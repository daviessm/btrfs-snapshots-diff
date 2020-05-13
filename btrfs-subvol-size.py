#!/usr/bin/env python3
import btrfs, os, sys

def file_sizes(fs, inum, this_subvol_id):
  freeable_size = 0

  min_key = btrfs.ctree.Key(inum, 0, 0)
  max_key = btrfs.ctree.Key(inum, -1, -1)
  # The special tree value of 0 will cause a search in the subvolume tree
  # that the inode which was used to open the file system object is part of.
  for header, data in btrfs.ioctl.search_v2(fs.fd, 0, min_key, max_key):
  #for header, data in btrfs.ioctl.search_v2(fs.fd, 0):
    item = btrfs.ctree.classify(header, data)
    #print("item " + str(type(item)) + " " + str(item))

    #Work on the file extent items (there could be more than one for a file)
    if isinstance(item, btrfs.ctree.FileExtentItem) and item.type == btrfs.ctree.FILE_EXTENT_REG and item.disk_num_bytes > 0:
      inodes, bytes_missed = btrfs.ioctl.logical_to_ino_v2(fs.fd, item.disk_bytenr, ignore_offset=True)
      if bytes_missed > 0:
        inodes, bytes_missed = btrfs.ioctl.logical_to_ino_v2(fs.fd, item.disk_bytenr, bufsize=65536+bytes_missed, ignore_offset=True)

      shared = False
      for inode in inodes:
        #print(str(item.disk_num_bytes) + " root " + str(inode.root))
        if inode.root != this_subvol_id:
          shared = True
          break

      if not shared:
        freeable_size += item.disk_num_bytes
  return freeable_size

def inspect_from(fs):
  inum = os.fstat(fs.fd).st_ino
  min_key = btrfs.ctree.Key(inum, 0, 0)
  max_key = btrfs.ctree.Key(inum, -1, -1)
  this_subvol_id = 0
  # The special tree value of 0 will cause a search in the subvolume tree
  # that the inode which was used to open the file system object is part of.
  for header, data in btrfs.ioctl.search_v2(fs.fd, 0, min_key, max_key):
    item = btrfs.ctree.classify(header, data)

    #Find the subvolume for this inode (always the first item)
    if isinstance(item, btrfs.ctree.InodeItem):
      inode_lookup_result = btrfs.ioctl.ino_lookup(fs.fd, objectid=item.objectid)
      this_subvol_id = inode_lookup_result.treeid
      print("Working on subvolume " + str(this_subvol_id))

  inodes = {}
  for dirname, subdirlist, filelist in os.walk(fs.path):
    for file in os.scandir(dirname):
      inodes[file.path] = file.inode()

  sizes = {}
  for path, inode in inodes.items():
    size = file_sizes(fs, inode, this_subvol_id)
    #print(path + " " + str(size))
    if size:
      sizes[path] = size

  total_size = 0
  sorted_sizes = sorted(sizes.items(), key=lambda x: x[1], reverse = True)
  for path, size in sorted_sizes:
    total_size += size
    if size > 256*1024: #Ignore files less than 256k
      print(str(total_size/1024/1024) + " " + "{:.1f}".format(size/1024/1024) + " " + path)

  print("Total size of exclusive extents: " + str(total_size))

def main():
  with btrfs.FileSystem(sys.argv[1]) as fs:
    results = inspect_from(fs)

if __name__ == '__main__':
  main()
