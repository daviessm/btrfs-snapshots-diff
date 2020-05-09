#!/usr/bin/env python3
import btrfs, os, sys

def file_backrefs(fs, inum, this_subvol_id):
  exclusive_backrefs = []

  min_key = btrfs.ctree.Key(inum, 0, 0)
  max_key = btrfs.ctree.Key(inum, -1, -1)
  # The special tree value of 0 will cause a search in the subvolume tree
  # that the inode which was used to open the file system object is part of.
  for header, data in btrfs.ioctl.search_v2(fs.fd, 0, min_key, max_key):
    item = btrfs.ctree.classify(header, data)

    #Work on the file extent items (there could be more than one for a file)
    if isinstance(item, btrfs.ctree.FileExtentItem) and item.type == btrfs.ctree.FILE_EXTENT_REG:
      key = btrfs.ctree.Key(item.disk_bytenr, btrfs.ctree.EXTENT_ITEM_KEY, item.disk_num_bytes)

      #Find its extent data items (there should just be one per file extent item)
      for header, data in btrfs.ioctl.search_v2(fs.fd, btrfs.ctree.EXTENT_TREE_OBJECTID, key, key + 1):
        extent_data_ref = btrfs.ctree.classify(header, data)

        #Get the list of extent data backrefs - file extent items that point at this extent
        is_referenced_elsewhere = False
        for backref in extent_data_ref.extent_data_refs:
          if backref.root != this_subvol_id:
            is_referenced_elsewhere = True
            break

        if not is_referenced_elsewhere:
          exclusive_backrefs.append(extent_data_ref)
  return exclusive_backrefs

def inspect_from(fs, root):
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
  for dirname, subdirlist, filelist in os.walk(root):
    for file in os.scandir(dirname):
      inodes[file.path] = file.inode()

  results = {}
  for path, inode in inodes.items():
    backrefs = file_backrefs(fs, inode, this_subvol_id)
    if backrefs:
      results[path] = backrefs

  sizes = {}
  for path, backrefs in results.items():
    size_mb = 0
    for backref in backrefs:
      size_mb = size_mb + (backref.length / 1024 / 1024)
    sizes[path] = size_mb

  total_size = 0
  sorted_sizes = sorted(sizes.items(), key=lambda x: x[1], reverse = True)
  for path, size in sorted_sizes:
    total_size += size
    print(str(size) + " " + path)

  print("Total size of exclusive extents: " + str(total_size))

def main():
  with btrfs.FileSystem(sys.argv[1]) as fs:
    results = inspect_from(fs, sys.argv[1])

if __name__ == '__main__':
  main()
