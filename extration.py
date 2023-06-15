import os
import sys
import argparse
import datetime
import time
import ctypes
import pytsk3
from tabulate import tabulate
import psutil
from tqdm import tqdm
import csv
import pandas as pd
import subprocess
import re
import curses

magics = {
    "jpg" : [b"\xff\xd8\xff\xe0\x00\x10\x4a\x46", b"\xff\xd9"],
    "png" : [b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a", b"\x49\x45\x4e\x44\xae\x42\x60\x82"],
    "pdf" : [b"\x25\x50\x44\x46", b"\x25\x25\x45\x4f\x46"],
    "gif" : [b"\x47\x49\x46\x38", b"\x00\x3b"],
    "xml" : [b"\x50\x4b\x03\x04\x14\x00\x06\x00", b"\x50\x4b\x05\x06"],
}

good_recovered_files = []
recoverable = {}
selected_files = {}
disk = 0

analyzeMFT_path = "./analyzeMFT/analyzeMFT.py"
mft_file_path = "./analyzeMFT/mft_tmp"
mft_parse_file_path = "./analyzeMFT/mft_tmp.csv"


def create_image_from_disk(disk_path, image_path):
    disk = rf"\\.\\{disk_path}"
    img_info = pytsk3.Img_Info(disk)
    with open(image_path, "wb") as output_file:
        offset = 0
        chunk_size = 1024 * 1024
        while offset < img_info.get_size():
            data = img_info.read(offset, chunk_size)
            output_file.write(data)
            offset += chunk_size
    print(f"Image {image_path} created successfully")

def print_directory_table(directory):
    table = [["Name", "Type", "Size", "Create Date", "Modify Date"]]
    for f in directory:
        name = f.info.name.name
        if f.info.meta.type == pytsk3.TSK_FS_META_TYPE_DIR:
            f_type = "DIR"
        else:
            f_type = "FILE"
        size = f.info.meta.size
        create = f.info.meta.crtime
        modify = f.info.meta.mtime
        table.append([name, f_type, size, create, modify])
    print(tabulate(table, headers="firstrow"))


def ft_read_disk(disk):
    image = pytsk3.Img_Info(disk)
    try:
        partitionTable = pytsk3.Volume_Info(image)
    except Exception as error:
        print(error)
        exit(1)
    try:
        fileSystemObject = pytsk3.FS_Info(image, offset=partitionTable[0].start*512)
    except Exception as error:
        print(error)
        exit(1)
    return fileSystemObject

def ft_parse_MFT(mft_file_path):
    command = ["python3", analyzeMFT_path, "-f", mft_file_path,  "-o", mft_parse_file_path]
    subprocess.run(command)

def ft_check_MFT(mft_parse_file_path):
    df = pd.read_csv(mft_parse_file_path, encoding="latin-1")
    for index, row in df.iterrows():
        good_value = row['Good']
        record_type = row['Record type']
        filename = row['Filename']
        modif_date = row['Modified Date']
        if pd.notnull(good_value):
            if good_value == 1 and record_type == "resident":
                recoverable[filename] = index

def ft_recover_file(image_file_path, index, output_file_path):
    try:
        command = ["fls", "-r", "-o", str(index), image_file_path]
        result = subprocess.run(command, stdout=subprocess.PIPE)
        inode = result.stdout
        inode = str(inode)[2:-3]
        command = ["icat", "-o", str(index), image_file_path, inode]
        result = subprocess.run(command, stdout=subprocess.PIPE)
        data = result.stdout
        output_file = open(output_file_path, "wb")
        output_file.write(data)
        output_file.close()
        good_recovered_files.append([output_file_path, inode])
    except Exception as error:
        print(error)
        exit(1)

def ft_recover_all_files(image_file_path):
    print("Recovering files...")
    for filename, index in recoverable.items():
        output_file_path = "./recovered_files/" + filename
        ft_recover_file(image_file_path, index, output_file_path)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--disk", help="Disk to recover")
    parser.add_argument("-i", "--image", help="Image to recover")
    args = parser.parse_args()
    image_file_path = "./image.dd"

    if args.disk is not None:
        create_image_from_disk(args.disk, image_file_path)
        disk = ft_read_disk(image_file_path)
    elif args.image is not None:
        disk = ft_read_disk(args.image)
    else:
        print("No disk or image specified")
        exit(1)

    ft_recover_all_files(image_file_path)
    print("Recovery complete")

if __name__ == "__main__":
    main()
