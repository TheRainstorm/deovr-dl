import threading
import queue
import os
import time
import requests
import argparse
import re
import json
import re

def parseCookieFile(cookie_file) -> dict:
    ''' parseCookieFile function used to convert
        NetScape cookies file into a dictionary '''
    # https://gist.github.com/h3ssan/28196d1b4361b96b9358e844e5bb5cf0
    
    cookies = {}
    with open (cookie_file) as file:
        for line in file:
            if not re.match(r'^\#', line):
                lineFields = line.strip().split('\t')
                try:
                    cookies[lineFields[5]] = lineFields[6]
                except IndexError:
                    pass
    
    return cookies

def sanitize_filename(filename):
    # windows forbidden characters
    forbidden_chars = r'[\\/:"*?<>|]'
    sanitized = re.sub(forbidden_chars, ' ', filename)
    return sanitized

def parse_web(url):
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0'
    }
    response = session.get(url, headers=headers)

    # extract videoData object
    match = re.search(r'videoData\s*:\s*(.*),\n', response.text)
    if not match:
        print('videoData parsing failed')
        return False, None

    video_data_json = match.group(1)
    video_data = json.loads(video_data_json)
    # print(json.dumps(video_data, indent=4))

    return True,video_data

def download_chunk_helper(url, start, end, stream=True):
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
    
def download_file(url, output_file='output.mp4'):
    tic = time.time()
    response = download_chunk_helper(url, 0, -1)
    with open(output_file, 'wb') as f:
        for chunk in response.iter_content(chunk_size=1024**2):
            if chunk:
                f.write(chunk)
                downloaded_bytes = f.tell()
                print(f"Downloaded {downloaded_bytes:,} bytes avg: {downloaded_bytes/(time.time()-tic)/1024**2:4.2f} MiB/s", end='\r')
        total_size = f.tell()
    print_speed(time.time() - tic, total_size)

stop_event = threading.Event()
def download_chunk(tid, result_queue, shared_data, lock, task_queue):
    while not stop_event.is_set():
        with lock:
            if task_queue.empty():
                break
            chunk_id, start, end = task_queue.get()
        print(f"{f'Thread {tid}: Downloading chunck':<30s} {chunk_id:3d}/{shared_data['chunk_num']:<3d}")
        
        try:
            response = download_chunk_helper(shared_data['url'], start, end)
            if response.status_code == 206:
                result_queue.put((tid, chunk_id, start, response.content))
            else:
                print(f'Thread {tid} Error: HTTP response code {response.status_code}, downloading {start:,}-{end:,}')
                result_queue.put((tid, chunk_id, -2, None))
        except Exception as e:
            print(f'Thread {tid} Exception {e}, downloading {start:,}-{end:,}')
            result_queue.put((tid, chunk_id, -2, None))
        
    result_queue.put((tid, -1, -1, None))
    print(f'Thread {tid} finished')

def download_file_in_chunks(url, start_offset=64, chunk_size=100 * 1024 * 1024, output_file='output.mp4', recover_file="", max_threads=4):
    tic = time.time()
    recover_mode = False
    task_finished = []
    if recover_file and os.path.exists(recover_file):
        with open(recover_file, 'r') as f:
            task_finished = json.load(f)
            recover_mode = True
    
    out_file = open(output_file, 'wb' if not recover_mode else 'r+b')
    # get total size
    response = download_chunk_helper(url, 0, start_offset-1)
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
        t = threading.Thread(target=download_chunk, args=(i, result_queue, shared_data, lock, task_queue))
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

def seconds_to_hms(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02}:{minutes:02}:{secs:02}"

def print_formats(src_list):
    for i, s in enumerate(src_list):
        print(f"{i}: \t{s['quality']} \t{s['width']:>5d}x{s['height']:<5d} \t{s['encoding']} \t{s['mimeType']}")
        
parser = argparse.ArgumentParser(description='Download url from deovr')
parser.add_argument('-u', '--url', help='URL of video page')
parser.add_argument('-O', '--output-dir', default='./', help='Output file dir')
parser.add_argument('-t', '--title', default='', help='Used to construct filename. If not set, parse title from web')
parser.add_argument('-y', '--overwrite', action="store_true", help='overwrite exist')
parser.add_argument('-C', '--cookie-file', default='', help='cookie file')
# format select
parser.add_argument('-F', '--list-format', action="store_true", help='list all available format')
parser.add_argument('-c', '--encoding', nargs='+', default='h264', help='filter selected encoding. e.g -c h264 h265, default only h264')
parser.add_argument('-f', '--select-format-idx', type=int, help='select format by index. If not set, select the best quality with filted encoding')

parser.add_argument('-n', '--thread-number', type=int, default=0, help='parallel download threads, 0 for original downloader')
parser.add_argument('-S', '--chunk-size', type=int,  default=20*1024**2, help='Download in chunks of n bytes, default 20 MiB')
args = parser.parse_args()

cookies = {}
if args.cookie_file:
    cookies = parseCookieFile(args.cookie_file)
session = requests.Session()
session.cookies.update(cookies)

# get video data
success, video_data = parse_web(args.url)
if not success:
    print('Failed to parse web')
    exit(-1)

print(f"**** Parsed data:")
print(f"** Title: {video_data['title']}")
print(f"** Angle: {video_data['angle']}")
print(f"** 3D Format: {video_data['format']}")
print(f"** Duration: {seconds_to_hms(video_data['duration'])}")

# format select
src_list = video_data['src']
src_list.sort(key=lambda x: int(x['quality'][:-1]))
if args.list_format:
    print_formats(src_list)
    exit(0)

if args.select_format_idx:
    selected_src = src_list[args.select_format_idx]
else:
    filter_src = [src for src in src_list if src['encoding'] in args.encoding]
    selected_src = filter_src[-1]  # best quality in filtered encoding

print(f"\n**** Download Param:")
print(f"** Select encoding: {selected_src['encoding']}")
print(f"** Selected quality: {selected_src['quality']}")
if args.thread_number!=0:
    print(f"** Chunk size {args.chunk_size/1024**2:.2f} MiB")
    print(f"** Threads: {args.thread_number}")

# download url
if not args.title:
    args.title = sanitize_filename(video_data['title'])

if not os.path.exists(args.output_dir):
    os.makedirs(args.output_dir, exist_ok=True)
filename = f"{args.title} - {selected_src['encoding']} {selected_src['quality']}"
output_file = os.path.join(args.output_dir, f"{filename}.mp4")
output_tmp_file = os.path.join(args.output_dir, f"{filename}.mp4.tmp")
recover_file = os.path.join(args.output_dir, f"{filename}.recover.json")

print(f"Download to: {output_file}")
if os.path.exists(output_file):
    print('File already exists')
    if not args.overwrite:
        print('Add -y to overwrite. \nExit')
        exit(0)

if args.thread_number == 0:
    download_file(selected_src['url'], output_file)
else:
    success = download_file_in_chunks(selected_src['url'], output_file=output_tmp_file, recover_file=recover_file, max_threads=args.thread_number, chunk_size=args.chunk_size)
    if success:
        print('Download successed')
        os.rename(output_tmp_file, output_file)
        print(f"File size: {os.path.getsize(output_file):,} bytes")
    else:
        print('Download failed, run again to recover')
