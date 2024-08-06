import os
import requests
import argparse
from bs4 import BeautifulSoup
import re
import json

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
        if 'window.vrPlayerSettings' in script.string:
            video_data_script = script.string
        break
    
    if not video_data_script:
        print('No script tag with window.vrPlayerSettings found')
        return False, None

    # extract videoData object
    match = re.search(r'videoData\s*:\s*(.*),\n', video_data_script)
    if not match:
        print('videoData not found')
        return False, None

    video_data_json = match.group(1)
    video_data = json.loads(video_data_json)
    # print(json.dumps(video_data, indent=4))
    
    parsed_data = {
        'title': video_data['title'],
        'src': video_data['src'],
    }
    return True,parsed_data

def download_file_in_chunks(url, start_offset=0, chunk_size=100 * 1024 * 1024, output_file='output.mp4'):
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7,en-GB;q=0.6,es;q=0.5,pt;q=0.4',
        'origin': 'https://deovr.com',
        'priority': 'i',
        'referer': 'https://deovr.com/',
        'sec-ch-ua': '"Not)A;Brand";v="99", "Microsoft Edge";v="127", "Chromium";v="127"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'video',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0'
    }

    # get video file total size
    total_size = 100 * 1024**3 # 100GB, impossible to get the real size
    # response = requests.head(url, headers=headers)
    # total_size = int(response.headers.get('content-length', 0))
    # print('Total file size:', total_size)

    with open(output_file, 'ab') as f:
        for start in range(start_offset, total_size, chunk_size):
            end = min(start + chunk_size - 1, total_size - 1)
            range_header = f'bytes={start}-{end}'
            chunk_headers = headers.copy()
            chunk_headers['Range'] = range_header
            response = requests.get(url, headers=chunk_headers, stream=True)

            if response.status_code == 206:  # 206 Partial Content
                f.write(response.content)
                print(f'Downloaded bytes {start}-{end}')
            elif response.status_code == 416:
                print("Final chunk")
                range_header = f'bytes={start}-'
                chunk_headers = headers.copy()
                chunk_headers['Range'] = range_header
                response = requests.get(url, headers=chunk_headers, stream=True)
                f.write(response.content)
                end = start + len(response.content) - 1
                print(f'Downloaded bytes {start}-{end}')
                break
            else:
                print('Error: HTTP response code', response.status_code)
                break

parser = argparse.ArgumentParser(description='Download url from deovr')
parser.add_argument('-u', '--url', help='URL of deovr web page')
parser.add_argument('-O', '--output-dir', default='./', help='Output file dir')
parser.add_argument('-t', '--title', default='', help='filename = <title>.mp4')

parser.add_argument('-c', '--code', default='h264', help='select codec')

parser.add_argument('-C', '--chunck-size', type=int,  default=100*1024**2, help='Download in chunks of n bytes')
# parser.add_argument('-S', '--start-offset', type=int, help='download skip the first n bytes', default=0)
args = parser.parse_args()

success, parsed_data = parse_web(args.url)
if not success:
    print('Failed to parse web')
    exit(-1)
print(f"Title: {parsed_data['title']}")

# get url
filter_url = []
for i,src in enumerate(parsed_data['src']):
    if src['encoding'] == args.code:
        filter_url.append((src['url'], src['quality']))

filter_url.sort(key=lambda x: x[1], reverse=True)

selected_url, selected_quality = filter_url[0]
print(f"Selected quality: {selected_quality}")

# download url
if not args.title:
    args.title = parsed_data['title']

output_file = os.path.join(args.output_dir, args.title + '.mp4')
print(f"Download to: {output_file}")

download_file_in_chunks(selected_url, output_file=output_file, chunk_size=args.chunck_size)
print('Download completed')
