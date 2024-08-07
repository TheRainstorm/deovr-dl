import threading
import queue
import os
import time
import requests
import argparse
from bs4 import BeautifulSoup
import re
import json

def sanitize_filename(filename):
    # windows forbidden characters
    forbidden_chars = r'[\\/:"*?<>|]'
    sanitized = re.sub(forbidden_chars, ' ', filename)
    return sanitized

def parse_web(url):
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0'
    }
    response = requests.get(url, headers=headers)
    
    soup = BeautifulSoup(response.text, 'lxml')

    script_tags = soup.find_all('script', type='text/javascript')
    
    # find script contains videoData
    video_data_script = None
    for script in script_tags:
        if 'videoData' in script.string:
            video_data_script = script.string
            break
    
    if not video_data_script:
        print('No script tag with videoData found')
        return False, None

    # extract videoData object
    match = re.search(r'videoData\s*:\s*(.*),\n', video_data_script)
    if not match:
        print('videoData parsing failed')
        return False, None

    video_data_json = match.group(1)
    video_data = json.loads(video_data_json)
    # print(json.dumps(video_data, indent=4))

    return True,video_data

def download_chunk_helper(url, start, end):
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0'
    }
    range_header = f'bytes={start}-{end}'
    chunk_headers = headers.copy()
    chunk_headers['Range'] = range_header
    response = requests.get(url, headers=chunk_headers, stream=True)
    return response

def download_chunk(tid, result_queue, shared_data, lock, task_queue):
    while True:
        with lock:
            if task_queue.empty():
                break
            start, end = task_queue.get()
        print(f"Thread {tid}: Downloading bytes {start:,}\t\t{end+1:,}")
        
        response = download_chunk_helper(shared_data['url'], start, end)

        if response.status_code == 206:
            result_queue.put((tid, start, response.content))
        else:
            print(f'Thread {tid} Error: HTTP response code {response.status_code}, downloading {start:,}-{end:,}')
            exit(-1)
    result_queue.put((tid, -1, None))
    print(f'Thread {tid} finished')

def download_file_in_chunks(url, start_offset=64, chunk_size=100 * 1024 * 1024, output_file='output.mp4', recover_file="", max_threads=4):
    tic = time.time()
    f = open(output_file, 'wb')
    # get total size
    response = download_chunk_helper(url, 0, start_offset-1)
    total_size = int(response.headers.get('Content-Range').split('/')[-1])
    f.write(response.content)
    
    task_queue = queue.Queue()
    for start in range(start_offset, total_size, chunk_size):
        end = min(start + chunk_size - 1, total_size - 1)
        task_queue.put((start, end))
    
    shared_data = {
        'url': url,
        'chunk_size': chunk_size,
        'total_size': total_size
    }
    lock = threading.Lock()

    result_queue = queue.Queue()
    for i in range(max_threads):
        t = threading.Thread(target=download_chunk, args=(i, result_queue, shared_data, lock, task_queue))
        t.start()
    
    count_finished = 0
    while True:
        tid, start, chunk = result_queue.get()
        if start == -1:
            count_finished += 1
            if count_finished == max_threads:
                break
            continue
        # print(f'Thread {tid}: Downloaded bytes {start}-{start + len(chunk) - 1}')
        f.seek(start)
        f.write(chunk)
    f.close()
    toc = time.time()
    speed = shared_data['total_size'] / (toc - tic)
    print(f"Download completed: {shared_data['total_size']:,}|{shared_data['total_size']/1024**2:.2f} MiB")
    print(f"Elapsed time: {seconds_to_hms(int(toc - tic))} Speed: {speed/1024**2:.2f} MiB/s")

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

parser.add_argument('-n', '--thread-number', type=int, default=6, help='parallel download threads, default 6')
parser.add_argument('-F', '--list-format', action="store_true", help='list all available format')
parser.add_argument('-c', '--encoding', nargs='+', default='h264', help='filter selected encoding')
parser.add_argument('-f', '--select-format-idx', type=int, help='select format by index. If not set, select the best quality with filted encoding')

parser.add_argument('-C', '--chunck-size', type=int,  default=20*1024**2, help='Download in chunks of n bytes, default 25 MiB')
parser.add_argument('-y', '--overwrite', action="store_true", help='overwrite exist')
args = parser.parse_args()

success, parsed_data = parse_web(args.url)
if not success:
    print('Failed to parse web')
    exit(-1)

print(f"**** Parsed data:")
print(f"** Title: {parsed_data['title']}")
print(f"** Angle: {parsed_data['angle']}")
print(f"** Format: {parsed_data['format']}")
print(f"** Duration: {seconds_to_hms(parsed_data['duration'])}")

src_list = parsed_data['src']
src_list.sort(key=lambda x: int(x['quality'][:-1]))
if args.list_format:
    print_formats(src_list)
    exit(0)

# get url
if not args.select_format_idx:
    filter_src = [src for src in src_list if src['encoding'] in args.encoding]
    selected_src = filter_src[-1]
else:
    selected_src = src_list[args.select_format_idx]
selected_url = selected_src['url']

print(f"\n**** Downloader Param:")
print(f"** Thread num: {args.thread_number}")
print(f"** Chunksize: {args.chunck_size:,}")
print(f"** Select encoding: {selected_src['encoding']}")
print(f"** Selected quality: {selected_src['quality']}")

# download url
if not args.title:
    args.title = sanitize_filename(parsed_data['title'])

if not os.path.exists(args.output_dir):
    os.makedirs(args.output_dir, exist_ok=True)
filename = f"{args.title} - {selected_src['encoding']} {selected_src['quality']}"
output_file = os.path.join(args.output_dir, f"{filename}.mp4")
recover_file = os.path.join(args.output_dir, f"{filename}.recover")

print(f"Download to: {output_file}")
if os.path.exists(output_file):
    print('File already exists')
    if not args.overwrite:
        print('Add -y to overwrite. \nExit')
        exit(0)
    
download_file_in_chunks(selected_url, output_file=output_file, recover_file=recover_file, chunk_size=args.chunck_size, max_threads=args.thread_number)
