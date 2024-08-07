import os
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

def download_chunk_helper(url, start, end):
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0'
    }
    range_header = f'bytes={start}-{end}'
    chunk_headers = headers.copy()
    chunk_headers['Range'] = range_header
    response = requests.get(url, headers=chunk_headers, stream=True)
    return response

def download_file(url, output_file='output.mp4'):
    tic = time.time()
    response = download_chunk_helper(url, 0, -1)
    with open(output_file, 'wb') as f:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
                print(f"Downloaded {f.tell():,} bytes", end='\r')
        total_size = f.tell()
    toc = time.time()
    speed = total_size / (toc - tic)
    print(f"Downloaded {total_size:,} bytes")
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
parser.add_argument('-y', '--overwrite', action="store_true", help='overwrite exist')
# format select
parser.add_argument('-F', '--list-format', action="store_true", help='list all available format')
parser.add_argument('-c', '--encoding', nargs='+', default='h264', help='filter selected encoding')
parser.add_argument('-f', '--select-format-idx', type=int, help='select format by index. If not set, select the best quality with filted encoding')
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
    
download_file(selected_src['url'], output_file)
