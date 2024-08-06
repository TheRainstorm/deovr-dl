## Intro

[DeoVR](https://deovr.com/) is a great VR video streaming platform. It features a large amount of user-uploaded content, including many high-quality videos such as cosplay convention, various tech expos, travel vlogs, and more. The video resolution is also very high, with regular users able to watch single-eye 4160p videos for free. However, DeoVR does have a downside: videos that were previously available for free may become exclusive to members after some time. Therefore, for videos you really like, it's crucial to download them.

Currently, only members of DeoVR can download 3 videos per month. And the yt-dlp project does not yet support the DeoVR website.

To address the above issues, this script is used to download videos from DeoVR offline.

## Usage

```shell
pip install -r requirements.txt
```

```shell
python deovr-dl.py -u https://deovr.com/oraehm          # download best quality video
python deovr-dl.py -O ./output -u https://deovr.com/oraehm       # specify output dir
python deovr-dl.py -O ./output -u https://deovr.com/oraehm -n 6  # download with 6 threads
python deovr-dl.py -u https://deovr.com/oraehm -F       # list all available format
python deovr-dl.py -u https://deovr.com/oraehm -f 0     # select format by index
```

help:

```shell
usage: deovr-dl.py [-h] [-u URL] [-O OUTPUT_DIR] [-t TITLE] [-n THREAD_NUMBER] [-F] [-c ENCODING [ENCODING ...]] [-f SELECT_FORMAT_IDX] [-C CHUNCK_SIZE]

Download url from deovr

options:
  -h, --help            show this help message and exit
  -u URL, --url URL     URL of video page
  -O OUTPUT_DIR, --output-dir OUTPUT_DIR
                        Output file dir
  -t TITLE, --title TITLE
                        Used to construct filename. If not set, parse title from web
  -n THREAD_NUMBER, --thread-number THREAD_NUMBER
                        parallel download threads, default 6
  -F, --list-format     list all available format
  -c ENCODING [ENCODING ...], --encoding ENCODING [ENCODING ...]
                        filter selected encoding
  -f SELECT_FORMAT_IDX, --select-format-idx SELECT_FORMAT_IDX
                        select format by index. If not set, select the best quality with filted encoding
  -C CHUNCK_SIZE, --chunck-size CHUNCK_SIZE
                        Download in chunks of n bytes, default 25 MiB

```
