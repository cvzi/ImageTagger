#!/usr/bin/env python3
# https://github.com/cvzi/ImageTagger
import gi
gi.require_version('GExiv2', '0.10')
from gi.repository import GExiv2
import tempfile
import os
import random
import shutil

# Setup
# { "filename1" : [Imagedata obj, bool haschanged] }
filequeue = dict() # Open files or files waiting to be written to disk


def copyFile(src, dest):
    buffer_size = min(1024*1024,os.path.getsize(src))
    if(buffer_size == 0):
        buffer_size = 1024
    with open(src, 'rb') as fsrc:
        with open(dest, 'wb') as fdest:
            shutil.copyfileobj(fsrc, fdest, buffer_size)

def saveToFile(threshold=20,force=False):
    global filequeue
    
    if not force and len(filequeue) < threshold:
        return

    tmpfiles = []
    temp_dir = tempfile.gettempdir()
    for filename in filequeue:
        if filequeue[filename][1]:
            try:
                tmpfile = os.path.join(temp_dir, "tags." + os.path.basename(filename.encode("utf-8", "ignore").decode("ascii","ignore")) + (".%d%s" % (random.randint(0,10000), os.path.splitext(filename)[1])))
                copyFile(filename,tmpfile)
                filequeue[filename][0].save_file(tmpfile)
                tmpfiles.append((tmpfile,filename))
            except Exception as e:
                print("Could not write to tmp file %s:" % tmpfile)
                print(e)
    for t in tmpfiles:
        copyFile(t[0],t[1])
    
    filequeue = dict()

def getTags(filename):
    global filequeue
    if filename in filequeue:
        img = filequeue[filename][0]
    else:
        img = Imagedata(filename)
        filequeue[filename] = [img,False]

    return getTagsFromImagedata(img)
    
def getTagsFromImagedata(img):
    tags = set();

    tags_iptc = img.get_multiple('Iptc.Application2.Keywords') or []
    tags_iptc = map(str.strip, tags_iptc)
    tags.update(tags_iptc)

    tags_xmp = img.get('Xmp.dc.subject')
    tags_xmp = tags_xmp.split(',') if tags_xmp is not None else []
    tags_xmp = map(str.strip, tags_xmp)
    tags.update(tags_xmp)

    return tags


def setTags(filename,tags):
    global filequeue
    if filename in filequeue:
        img = filequeue[filename][0]
        filequeue[filename][1] = True # Set flag, because file will be changed
    else:
        img = Imagedata(filename)
        filequeue[filename] = [img,True]
    
    tags = sorted(tags);

    try:
        del img['Iptc.Application2.Keywords']
    except:
        pass
    try:
        del img['Xmp.dc.subject']
    except:
        pass
    
    img.set_multiple('Iptc.Application2.Keywords',tags)
    img.set('Xmp.dc.subject',', '.join(tags))

    saveToFile()

#https://git.gnome.org/browse/gexiv2/tree/gexiv2/gexiv2-metadata.h
class Imagedata(GExiv2.Metadata):
    def __init__(self, filename):
        super(Imagedata, self).__init__()
        with open(filename, "rb") as filebuffer:
            self.open_buf(filebuffer.read())
    
    def save_file(self, path):
        super(Imagedata, self).save_file(path)
        
    def get_tags(self):
        return self.get_exif_tags() + self.get_iptc_tags() + self.get_xmp_tags()
    
    def get(self, key, default=None):
        return self.get_tag_string(key) if self.has_tag(key) else default

    def set(self, key, value):
        return self.set_tag_string(key,value)

    def get_multiple(self, key, default=None):
        return self.get_tag_multiple(key) if self.has_tag(key) else default

    def set_multiple(self, key, values):
        return self.set_tag_multiple(key, values)
    
    def __iter__(self):
        return iter(self.get_tags())
    
    def __contains__(self, key):
        return self.has_tag(key)
    
    def __len__(self):
        return len(self.get_tags())
    
    def __getitem__(self, key):
        if self.has_tag(key):
            return self.get_tag_string(key)
        else:
            raise KeyError('%s: Unknown tag' % key)
    
    def __delitem__(self, key):
        if self.has_tag(key):
            self.clear_tag(key)
        else:
            raise KeyError('%s: Unknown tag' % key)
    
    __setitem__ = GExiv2.Metadata.set_tag_string


