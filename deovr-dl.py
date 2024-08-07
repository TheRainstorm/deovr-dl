from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import os
import threading
import time
import requests
import argparse
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
    range_header = f'bytes={start}-{end}'
    chunk_headers = headers.copy()
    chunk_headers['Range'] = range_header
    response = requests.get(url, headers=chunk_headers, stream=stream)
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

def download_file_in_chunks(url, start_offset=64, chunk_size=100 * 1024 * 1024, output_file='output.mp4', max_threads=4):
    tic = time.time()
    def download_chunk(url, chunk_id, start, end):
        thread_id = threading.current_thread().name.split('_')[-1]
        thread_name = f'Thread {thread_id}'
        print(f'{f"{thread_name} Downloading chunk":30s} {chunk_id:3d}/{chunk_num:<3d}')
        
        response = download_chunk_helper(url, start, end, stream=False)
        if response.status_code != 206:
            return -1, -1, None
        return chunk_id, start, response
    
    with open(output_file, 'wb') as f:
        # get video file total size
        response = download_chunk_helper(url, 0, start_offset-1)
        total_size = int(response.headers.get('Content-Range').split('/')[-1])
        f.write(response.content)
    
        futures = []
        chunk_num = math.ceil((total_size - start_offset) / chunk_size)
        with ThreadPoolExecutor(max_threads) as executor:
            for start in range(start_offset, total_size, chunk_size):
                end = min(start + chunk_size - 1, total_size - 1)
                chunk_id = len(futures)
                futures.append(executor.submit(download_chunk, url, chunk_id, start, end))
        
            for future in as_completed(futures):
                chunk_id, start, response = future.result()
                print(f'{"         Downloaded chunk":<30s} {chunk_id:3d}')
                if response:
                    f.seek(start)
                    f.write(response.content)
                else:
                    print('Failed to download chunk')
                    exit(-1)
    print_speed(time.time() - tic, total_size)

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
# format select
parser.add_argument('-F', '--list-format', action="store_true", help='list all available format')
parser.add_argument('-c', '--encoding', nargs='+', default='h264', help='filter selected encoding')
parser.add_argument('-f', '--select-format-idx', type=int, help='select format by index. If not set, select the best quality with filted encoding')

parser.add_argument('-n', '--thread-number', type=int, default=0, help='parallel download threads, 0 for original downloader')
parser.add_argument('-C', '--chunck-size', type=int,  default=20*1024**2, help='Download in chunks of n bytes, default 20 MiB')
args = parser.parse_args()

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
    print(f"** Chunk size {args.chunck_size/1024**2:.2f} MiB")
    print(f"** Threads: {args.thread_number}")

# download url
if not args.title:
    args.title = sanitize_filename(video_data['title'])

if not os.path.exists(args.output_dir):
    os.makedirs(args.output_dir, exist_ok=True)
filename = f"{args.title} - {selected_src['encoding']} {selected_src['quality']}"
output_file = os.path.join(args.output_dir, f"{filename}.mp4")

print(f"Download to: {output_file}")
if os.path.exists(output_file):
    print('File already exists')
    if not args.overwrite:
        print('Add -y to overwrite. \nExit')
        exit(0)

if args.thread_number == 0:
    download_file(selected_src['url'], output_file)
else:
    download_file_in_chunks(selected_src['url'], output_file=output_file, max_threads=args.thread_number, chunk_size=args.chunck_size)
