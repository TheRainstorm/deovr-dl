import json
import os
import queue
import threading
import time

def seconds_to_hms(seconds):
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02}:{minutes:02}:{secs:02}"

def download_chunk_helper(session, url, start, end, stream=True):
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0'
    }
    end = '' if end == -1 else end
    range_header = f'bytes={start}-{end}'
    chunk_headers = headers.copy()
    chunk_headers['Range'] = range_header
    response = session.get(url, headers=chunk_headers, stream=stream, timeout=(10, 5))  # set timeout, so don't hang long time
    return response

def print_speed(seconds, total_size):
    speed = total_size / seconds
    print(f"Downloaded {total_size:,} bytes")
    print(f"Elapsed time: {seconds_to_hms(seconds)} Speed: {speed/1024**2:.2f} MiB/s")
    
def download_file(session, url, output_file='output.mp4', print_info=False, repeat=1):
    '''donwload file single thread
    '''
    while True:
        repeat -= 1
        try:
            tic = time.time()
            response = download_chunk_helper(session, url, 0, -1)
            with open(output_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024**2):
                    if chunk:
                        f.write(chunk)
                        downloaded_bytes = f.tell()
                        if print_info:
                            print(f"Downloaded {downloaded_bytes:,} bytes avg: {downloaded_bytes/(time.time()-tic)/1024**2:4.2f} MiB/s", end='\r')
                total_size = f.tell()
            if print_info:
                print_speed(time.time() - tic, total_size)
            
            return True
        except KeyboardInterrupt:
            print("KeyboardInterrupt")
            os.path.remove(output_file)
            return False
        except Exception as e:
            print(f"Exception {e}, repeat {repeat}")
            if repeat <= 0:
                return False

stop_event = threading.Event()
def download_chunk_thread(session, tid, result_queue, shared_data, lock, task_queue, repeat=1):
    while not stop_event.is_set():
        with lock:
            if task_queue.empty():
                break
            chunk_id, start, end = task_queue.get()
        print(f"{f'Thread {tid}: Downloading chunck':<30s} {chunk_id:3d}/{shared_data['chunk_num']:<3d}")
        
        while not stop_event.is_set():
            repeat -= 1
            try:
                response = download_chunk_helper(session, shared_data['url'], start, end)
                if response.status_code == 206:
                    result_queue.put((tid, chunk_id, start, response.content))
                else:
                    print(f'Thread {tid} Error: HTTP response code {response.status_code}, downloading {chunk_id} {start:,}-{end:,}')
                    result_queue.put((tid, chunk_id, -2, None))
                break
            except Exception as e:
                print(f'Thread {tid} Exception {e}, downloading {chunk_id}, repeat {repeat}')
                if repeat<= 0:
                    result_queue.put((tid, chunk_id, -2, None))
                    break
        
    result_queue.put((tid, -1, -1, None))
    print(f'Thread {tid} finished')

def download_file_in_chunks(session, url, start_offset=64, chunk_size=100 * 1024 * 1024, output_file='output.mp4', recover_file="", max_threads=4, repeat=1):
    '''donwload file multi thread
    '''
    tic = time.time()
    recover_mode = False
    task_finished = []
    if recover_file and os.path.exists(recover_file):
        with open(recover_file, 'r') as f:
            task_finished = json.load(f)
            recover_mode = True
    
    out_file = open(output_file, 'wb' if not recover_mode else 'r+b')
    # get total size
    repeat_t = repeat
    while True:
        repeat_t -= 1
        try:
            response = download_chunk_helper(session, url, 0, start_offset-1)
            break
        except Exception as e:
            if repeat_t <= 0:
                print(f"Get total size failed")
                print(f"Exception {e}, repeat {repeat}")
                return False
    total_size = int(response.headers.get('Content-Range').split('/')[-1])
    out_file.write(response.content)
    
    lock = threading.Lock()
    task_queue = queue.Queue()
    chunk_id = 0
    for start in range(start_offset, total_size, chunk_size):
        end = min(start + chunk_size - 1, total_size - 1)
        if chunk_id not in task_finished:  # not downloaded
            task_queue.put((chunk_id, start, end))
        chunk_id += 1
    chunk_num = chunk_id
    
    if recover_mode:
        remain = task_queue.qsize()/chunk_num
        print(f"Recovered {1 - remain:.2f}, remain {remain:.2f}")

    shared_data = {
        'url': url,
        'chunk_num': chunk_num,
    }
    
    result_queue = queue.Queue()
    threads = []
    for i in range(max_threads):
        t = threading.Thread(target=download_chunk_thread, args=(session, i, result_queue, shared_data, lock, task_queue, repeat))
        t.start()
        threads.append(t)
    
    success = True
    count_finished = 0
    download_bytes = 0
    try:
        while True:
            tid, chunk_id, start, chunk = result_queue.get()
            if start == -1:  # download finished
                count_finished += 1
                if count_finished == max_threads:
                    break
                continue
            elif start == -2:  # download error
                success = False
                continue
            print(f'{"         Downloaded chunk":<30s} {chunk_id:3d}')
            out_file.seek(start)
            out_file.write(chunk)
            download_bytes += len(chunk)
            task_finished.append(chunk_id)
    except KeyboardInterrupt:
        print("KeyboardInterrupt, saving recover file")
        print(task_finished)
        task_finished.sort()
        with open(recover_file, 'w') as f:
            json.dump(task_finished, f, indent=4)
        
        out_file.close()
        
        stop_event.set()
        for t in threads:
            t.join()
        print("All threads stopped, exit")
        exit(0)
    
    out_file.close()
    if not success:
        with open(recover_file, 'w') as f:
            json.dump(task_finished, f, indent=4)
    else:
        if os.path.exists(recover_file):
            os.remove(recover_file)
    
    toc = time.time()
    speed = download_bytes / (toc - tic)
    print(f"Download bytes: {download_bytes:,}|{download_bytes/1024**2:.2f} MiB")
    print(f"Elapsed time: {seconds_to_hms(int(toc - tic))} Speed: {speed/1024**2:.2f} MiB/s")
    return success
