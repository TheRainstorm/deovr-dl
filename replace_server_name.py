

import argparse
import json
import re
import os


def rewrite_file(file_path, server, replace_server):
    def strip_end_slash(s):
        if s.endswith('/'):
            return s[:-1]
        return s

    with open(file_path) as f:
        text = f.read()
    new_text = text.replace(strip_end_slash(server), strip_end_slash(replace_server))
    with open(file_path, 'w') as f:
        f.write(new_text)
    return new_text

parser = argparse.ArgumentParser(description='Download url from deovr')
parser.add_argument('-T', '--root-dir', required=True, help='DeoVR root dir')
parser.add_argument('-S', '--server', default="http://localhost:8000", help='Old HTTP server address')
parser.add_argument('-R', '--replace-server', default="http://localhost:8000", help='New HTTP server address will replace')

parser.add_argument('-d', '--dry-run', action="store_true", help='test replace first and quit')
args = parser.parse_args()

root_dir = args.root_dir

playlist_info = {}
for playlist in os.listdir(root_dir):
    playlist_path = os.path.join(root_dir, playlist)
    if not os.path.isdir(playlist_path):
        continue
    if 'metadata' in os.listdir(playlist_path):
        playlist_info[playlist] = 0  # cnt of files
        
        json_dir = os.path.join(root_dir, playlist, 'metadata/json')
        
        for title_json in os.listdir(json_dir):
            text = rewrite_file(os.path.join(json_dir, title_json), args.server, args.replace_server)
            
            playlist_info[playlist] += 1
            if args.dry_run:
                print("Dry run, replace first and quit")
                print(f"{playlist}/{title_json}: ")
                print(f"{text}")
                exit(0)
                
        
rewrite_file(os.path.join(root_dir, 'top.json'), args.server, args.replace_server)
# print summary
for playlist in playlist_info:
    print(f"{playlist}: {playlist_info[playlist]}")
