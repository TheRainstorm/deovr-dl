import argparse
import glob
import json
import re
import os
import shutil

from generate_json import add_to_top_json, read_top_json, write_top_json, del_top_json

parser = argparse.ArgumentParser(description='DeoVR video library tool')
parser.add_argument('-T', '--root-dir', required=True, help='DeoVR root dir')
# parser.add_argument('-S', '--server', default="http://localhost:8000", help='Old HTTP server address')

subparsers = parser.add_subparsers(title="command", dest="command")

# move
parser_move = subparsers.add_parser("move", help="move playlist to another playlist")
parser_move.add_argument("--src", required=True, help="from playlist")
parser_move.add_argument("--dst", required=True, help="to playlist")
parser_move.add_argument('-V', '--title', help='only move one video title')

# rename
# TODO
parser_rename = subparsers.add_parser("rename", help="rename playlist")
parser_rename.add_argument("--src", required=True, help="old name")
parser_rename.add_argument("--dst", required=True, help="new name")

# list
parser_list = subparsers.add_parser("list", help="list playlist info")
# TODO

args = parser.parse_args()

if args.command == "move":
    json_dir = os.path.join(args.root_dir, args.src, "metadata", "json")
    title_list = []
    if args.title:
        title_list = [args.title]
    else:
        for file in os.listdir(json_dir):
            if file.endswith(".json"):
                title, ext = os.path.splitext(file)
                title_list.append(title)
    for title in title_list:
        print(f"Moving {title}")
        json_path = os.path.join(args.root_dir, args.src, "metadata", "json", f"{title}.json")
        with open(json_path, "r") as f:
            json_text = f.read()
        
        # update json
        json_text_new = re.sub(rf'/{args.src}/', f'/{args.dst}/', json_text)
        with open(json_path, "w") as f:
            f.write(json_text_new)
        video_json = json.loads(json_text_new)
        
        def move_files(src_dir, dst_dir, title):
            videos = glob.glob(os.path.join(src_dir, glob.escape(title)+"*"))
            for video in videos:
                try:
                    shutil.move(video, dst_dir)
                except Exception as e:
                    print(f"{e}")
            return len(videos)
        
        # move video
        num = move_files(os.path.join(args.root_dir, args.src, ), os.path.join(args.root_dir, args.dst), title)
        # move metadata
        move_files(os.path.join(args.root_dir, args.src, "metadata", "thumbnail"), os.path.join(args.root_dir, args.dst, "metadata", "thumbnail"), title)
        move_files(os.path.join(args.root_dir, args.src, "metadata", "preview"), os.path.join(args.root_dir, args.dst, "metadata", "preview"), title)
        move_files(os.path.join(args.root_dir, args.src, "metadata", "seeklookup"), os.path.join(args.root_dir, args.dst, "metadata", "seeklookup"), title)
        move_files(os.path.join(args.root_dir, args.src, "metadata", "json"), os.path.join(args.root_dir, args.dst, "metadata", "json"), title)
        
    # # update top json
    # for title in title_list:
        del_top_json(args.root_dir, args.src, title)
        add_to_top_json(args.root_dir, args.dst, [video_json])
    # remove ori playlist
    input(f"Remove {args.src} playlist? Press Enter to continue...")
    shutil.rmtree(os.path.join(args.root_dir, args.src))
else:
    print("Not implemented")
    exit(1)
