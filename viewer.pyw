#!/usr/bin/env python3
# https://github.com/cvzi/ImageTagger
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GObject
import sys
import os
import pickle
import hashlib
import time
import subprocess
import tempfile
import math
from Imagedata import *
from send2trash import send2trash

class KeyShortcuts():
    def __init__(self, window):
        self.keys = ""
        self.win = window
    
    def reset(self):
        if self.keys:
            self.__find_tag(self.keys)
        
        self.keys = ""
            
    def add(self, key):
        self.keys += key

    def __tag_search_weight(self, tag, query):
        total = 0

        if not tag.startswith(query[0]):
            return 10000

        
        for char in query:
            if char in tag and char in query:
                index = tag.index(char)
                total += index
                tag = tag[index+1:]
                query = query[query.index(char)+1:]
            else:
                return 10000
        return total  
    def __find_tag(self, s):
        if not self.win.filename:
            return
        
        if s in self.win.allTags:
            self.__add_tag(s)
        else:
            matches = [tag for tag in self.win.allTags if tag.startswith(s)]
            if len(matches) == 1:
                self.__add_tag(matches[0])
            else:
                # select best approximate match
                weights = [(self.__tag_search_weight(tag, s),tag) for tag in self.win.allTags]
                weights.sort()
                if weights[0][0] < 10000 and weights[0][0] != weights[1][0]:
                    self.__add_tag(weights[0][1])
                else:
                    # Non existent tag
                    pass
        
    def __add_tag(self, s):
        if not self.win.filename:
            return
        
        tags = getTags(self.win.filename)
        tags.add(s)
        if self.win.lockTags:
            self.win.lockTagsList.add(s)
                
        # Save to file
        setTags(self.win.filename,tags)
        
        if not s in self.win.allTags:
            self.win.allTags = sorted(self.win.allTags+[s])
            self.win.showAllTags()
        
        self.win.updateImage()

class CircularIndex:
    def __init__(self,n):
        self.n = n
        self.i = 0

    def get(self,i):
        if i >= 0 and i < self.n:
            return i
        else:
            if i >= self.n:
                return i % self.n
            else:
                return (self.n + i) % self.n
            
class ButtonWindow:

    def __init__(self,gladefile,directory="."):
    
        self.directory = directory
        self.allImages = []
        self.allTags = []
        self.allTagsPerImage = {}
        self.allTagsButtons = {}
        self.index = 0
        self.lastSearch = ""
        self.lockTags = False
        self.lockTagsList = set()
        
        self.keyShortcuts = KeyShortcuts(self)
        
        self.builder = Gtk.Builder()
        self.builder.add_from_file(gladefile)
        
        self.window = self.builder.get_object("window1")

        self.window.connect("delete-event", Gtk.main_quit)
        self.window.connect("check_resize", self.on_check_resize)
        self.window.connect("key-press-event",self.on_key_press)   

        # File chooser
        self.buttonOpenFile = self.builder.get_object("buttonOpenFile")
        self.buttonOpenFile.connect("clicked",self.on_open_file_chooser)
        self.filechooserdialog = self.builder.get_object("filechooserdialog1")
        self.builder.get_object("buttonCloseFileChooser").connect("clicked",self.on_close_file_chooser)
        self.builder.get_object("buttonOpenNewPath").connect("clicked",self.on_open_new_path)
        self.filechooserdialog.connect("selection-changed",self.on_file_selection_changed)
        self.entryCurrentPath = self.builder.get_object("entryCurrentPath")

        # Image
        self.box = self.builder.get_object("scrolledwindow1")
        self.pixbuf = GdkPixbuf.Pixbuf()
        self.image_width = self.pixbuf.get_width() 
        self.image_height = self.pixbuf.get_height()
        self.image = self.builder.get_object('image1')
        self.image.set_from_stock(Gtk.STOCK_NEW,Gtk.IconSize.DIALOG)
        self.lastResize = None
        self.labelCurrentFile = self.builder.get_object("labelCurrentFile")
        self.labelCurrentFile.connect("clicked",self.on_open_in_browser)
        

        # Navigation
        self.builder.get_object("buttonGoBack").connect("clicked",self.on_back)
        self.builder.get_object("buttonGoForward").connect("clicked",self.on_forward)
        self.labelTotalImages = self.builder.get_object("labelTotalImages")
        
        # Search
        self.builder.get_object("searchField").connect("key-release-event",self.on_search)

        # Sorting
        self.sortby_store = sortby_store = Gtk.ListStore(str, str)
        sortby_store.append(["alphabetical", "A-Z"])
        sortby_store.append(["-alphabetical", "Z-A"])
        sortby_store.append(["numberoftags", "Least tags first"])
        sortby_store.append(["-numberoftags", "Most tags first"])
        sortby_store.append(["alphabeticaldirs", "A-Z folder name"])
        sortby_store.append(["-alphabeticaldirs", "Z-A folder name"])
        
        self.sortByCombo = self.builder.get_object("sortBy")
        self.builder.get_object("hbox2").remove(self.sortByCombo)
        self.sortByCombo = Gtk.ComboBox.new_with_model_and_entry(sortby_store)
        self.sortByCombo.set_entry_text_column(1)
        self.builder.get_object("hbox2").add(self.sortByCombo)
        self.sortByCombo.connect("changed", self.on_sort_by)

        # Delete button
        self.builder.get_object("buttonDeleteImage").connect("clicked",self.on_delete)

        # Tags
        self.boxAllTags = self.builder.get_object("boxAllTags")
        self.builder.get_object("buttonSaveNewTag").connect("clicked",self.on_save_new_tag)
        self.entryNewTag = self.builder.get_object("entryNewTag")
        self.entryNewTag.connect("activate",self.on_save_new_tag)


        # Lock checkbox
        self.checkLockButton = self.builder.get_object("checkLockTags")
        recordimg = Gtk.Image()
        recordimg.set_from_stock(Gtk.STOCK_MEDIA_RECORD, Gtk.IconSize.BUTTON)
        self.checkLockButton.add(recordimg)
        recordimg.show()
        self.checkLockButton.set_active(self.lockTags)
        self.checkLockButton.connect("toggled",self.on_check_lock)

        # Previews
        self.hboxPreviews = self.builder.get_object("hboxPreviews")
        self.previewholder = None

        self.loadDirectory()

    def openImage(self,filename=None):
        if filename is None and self.index < len(self.allImages):
            filename = self.allImages[self.index]

        loaded = True
        try:
            # Try loading the image
            self.pixbuf = GdkPixbuf.Pixbuf().new_from_file(filename)
            self.image_width = self.pixbuf.get_width() 
            self.image_height = self.pixbuf.get_height()
            self.image.set_from_pixbuf(self.pixbuf)
        except:
            # Try copying the file to temporary directory to avoid filename encoding problems
            try:
                temp_dir = tempfile.gettempdir()
                temp_file = os.path.join(temp_dir, ("imagefile.%s.%d%s" % (os.path.basename(filename.encode("utf-8", "ignore").decode("ascii","ignore")),random.randint(0,1000000), os.path.splitext(filename)[1])))
                copyFile(filename, temp_file)
                self.pixbuf = GdkPixbuf.Pixbuf().new_from_file(temp_file)
                os.remove(temp_file)
                self.image_width = self.pixbuf.get_width() 
                self.image_height = self.pixbuf.get_height()
                self.image.set_from_pixbuf(self.pixbuf)
            except:
                loaded = False
        
        if not loaded:
            self.filename = None
            self.pixbuf = None
            self.image.set_from_stock(Gtk.STOCK_DIALOG_ERROR,Gtk.IconSize.DIALOG)
            self.labelTotalImages.set_text("Error!")
        else:
            self.filename = filename
            self.labelCurrentFile.set_label(self.filename)
            self.on_check_resize(None,True)
            tags = getTags(filename)
            self.showSelectedTags(tags)
            self.labelTotalImages.set_text("%d/%d"%(self.index+1,len(self.allImages)))
            if self.previewholder:
                self.previewholder.update(self.allImages,self.index)

    def setButtonFontColor(self,button,color='#FFFFFF'):
        label = button.get_children()[0]
        label.modify_fg(Gtk.StateType.NORMAL, Gdk.color_parse(color))
                

    def showSelectedTags(self,tags):
        org = tags.copy()

        for tag in self.allTagsButtons:
            if self.lockTags and tag in self.lockTagsList:
                self.setButtonFontColor(self.allTagsButtons[tag],'#0BAA0F')
            else:
                self.setButtonFontColor(self.allTagsButtons[tag],'#000000')
                
            self.allTagsButtons[tag].handler_block_by_func(self.on_tag_click) # block "clicked" handler
            if tag in tags:
                self.allTagsButtons[tag].set_active(True)
                tags.remove(tag)

                    
            else:
                self.allTagsButtons[tag].set_active(False)
            self.allTagsButtons[tag].handler_unblock_by_func(self.on_tag_click)

        if len(tags) > 0:
            # the remaining tags are not yet in allTags i.e. the image was changed outside the application
            self.allTags = sorted(self.allTags + list(tags))
            self.showAllTags()
                

    def loadDirectory(self):
        self.allImages,self.allTags,self.allTagsPerImage = openDirectory(self.directory)
        self.allImagesORG = self.allImages.copy()
        
        self.index = 0

        self.allTags = sorted(self.allTags)
        
        self.showAllTags()

        if len(self.allImages) == 0:
            self.openImage(None)
            self.labelTotalImages.set_text("No images")
        else:
            self.openImage(self.allImages[0])
            self.labelTotalImages.set_text("%d/%d"%(self.index+1,len(self.allImages)))

        self.showPreviews()


    def search(self,s):
        s = s.lower()

        
        s = s.split("+")
        s = map(str.strip,s)
        s = [i for i in s if i]
        print(s)

        if len(s) == 0:
            self.allImages = self.allImagesORG.copy()
        else:
            if s == self.lastSearch:
                return
            self.lastSearch = s
            
            self.allImages = []

            # Normal search
            for image in self.allImagesORG:
                # Filename       
                found = 0
                for searchstr in s:
                    if searchstr in image.lower():
                        found += 1
                    if found == len(s):
                        self.allImages.append(image)
                        break

                # Tags
                found = 0
                for tag in self.allTagsPerImage[image]:
                    for searchstr in s:
                        if tag.lower().find(searchstr) != -1:
                            found += 1
                    if found == len(s):
                        self.allImages.append(image)
                        break
            
        self.index = 0
        if len(self.allImages) == 0:
            self.openImage(None)
            self.labelTotalImages.set_text("No images")
        else:
            self.openImage(self.allImages[self.index])
            self.labelTotalImages.set_text("%d/%d"%(self.index+1,len(self.allImages)))

    def sort(self,how):

        if how.endswith('alphabetical'):
            self.allImages = sorted(self.allImages,reverse=how[0]=="-") 
        elif how.endswith('numberoftags'):
            self.allImages = sorted(self.allImages,key=lambda image: len(self.allTagsPerImage[image]),reverse=how[0]=="-")
        elif how.endswith('alphabeticaldirs'):
            slash = "/"
            try:
                os.path.dirname(self.allImages[0]).rindex(slash)
            except:
                slash = "\\"
            self.allImages = sorted(self.allImages,key=lambda image: os.path.dirname(image)[os.path.dirname(image).rindex(slash)+1:],reverse=how[0]=="-")

            
        self.index = 0
        if len(self.allImages) == 0:
            self.openImage(None)
            self.labelTotalImages.set_text("No images")
        else:
            self.openImage(self.allImages[0])
            self.labelTotalImages.set_text("%d/%d"%(self.index+1,len(self.allImages)))

    class Preview:
        def __init__(self,window,imagefile,maxwidth=100,maxheight=100):
            self.filename = imagefile
            # Try loading the file
            try:
                pixbuf = GdkPixbuf.Pixbuf().new_from_file(self.filename)
            except gi.repository.GLib.GError as e:
                # Try copying the file to temporary directory to avoid filename encoding problems
                try:
                    temp_dir = tempfile.gettempdir()
                    temp_file = os.path.join(temp_dir, ("previewfile.%s.%d%s" % (os.path.basename(self.filename.encode("utf-8", "ignore").decode("ascii","ignore")),random.randint(0,1000000), os.path.splitext(self.filename)[1])))
                    copyFile(self.filename, temp_file)
                    pixbuf = GdkPixbuf.Pixbuf().new_from_file(temp_file)
                    os.remove(temp_file)
                except:
                    # Show "missing image" icon
                    pixbuf = Gtk.Window.render_icon_pixbuf(window,Gtk.STOCK_MISSING_IMAGE,Gtk.IconSize.DIALOG)
                    

            # Scale image
            self.width = w = pixbuf.get_width() 
            self.height = h = pixbuf.get_height()
                
            if h > maxheight:
                scale = maxheight / h
                w *= scale
                h *= scale

            if w > maxwidth:
                scale = maxwidth / w
                w *= scale
                h *= scale

            self.pixbuf_scaled = pixbuf.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
            del pixbuf

                
            

        def setImage(self,image):
            image.set_from_pixbuf(self.pixbuf_scaled)
            return image

    class PreviewHolder:
        def __init__(self,window,n,box,maxcache=100,w=100,h=100):
            self.n = n
            self.center = math.floor(self.n/2)
            self.places = [Gtk.Image() for i in range(n)]
            self.cache = {}
            self.maxcache = maxcache
            self.width = w
            self.height = h
            self.box = box
            self.window = window

        def update(self,allImages,index):
            if index >= len(allImages):
                self._pack()
                return
            
            
            self._setImage(self.center, allImages[index])
            ci = CircularIndex(len(allImages))
            for i in range(self.center):
                # Left
                self._setImage(self.center-i-1, allImages[ci.get(index-i-1)])
                # Right
                self._setImage(self.center+i+1, allImages[ci.get(index+i+1)])

            self._pack()


        def _pack(self):
            children = self.box.get_children()
            
            if len(children) < len(self.places):
                # First run: populate hbox:
                for gtkimage in self.places:
                    self.box.pack_start(gtkimage,False,False,0)
            else:
                # Consecutive run: just replace old images with new ones
                i = 0
                for child in children:
                    child.set_from_pixbuf(self.places[i].get_pixbuf())
                    i += 1

        def _setImage(self, i, image):
            if image in self.cache:
                preview = self.cache[image]
            else:
                preview = ButtonWindow.Preview(self.window,image,self.width,self.height)
                if len(self.cache) > self.maxcache:
                    self.cache = {}
                self.cache[image] = preview

            return preview.setImage(self.places[i])

        def _removeImage(self, i):
            self.places[i].set_from_stock(Gtk.STOCK_NEW,Gtk.IconSize.DIALOG)
            return self.places[i]
        
        

    def showPreviews(self):
        self.previewholder = self.PreviewHolder(self.window,15,self.hboxPreviews)
        self.previewholder.update(self.allImages,self.index)
        

    def showAllTags(self):

        # Clean up old tags
        for tag in self.allTagsButtons:
            self.allTagsButtons[tag].destroy()
        self.allTagsButtons = {}

        # Clean up empty hboxes
        for hbox in self.boxAllTags.get_children():
            hbox.destroy()

        box = Gtk.HBox(False,3)
        self.boxAllTags.pack_start(box, False, True, 5)
        box.show()
        i = 0
        for tag in self.allTags:
            button = Gtk.ToggleButton(tag)
            button.clickHandler = button.connect("clicked",self.on_tag_click,tag)
            self.allTagsButtons[tag] = button
            box.pack_start(button, False, True, 0)
            button.show()
            if i > 15:
                box = Gtk.HBox(False,3)
                self.boxAllTags.pack_start(box, False, True, 5)
                box.show()
                i = 0
            i += 1
        
        self.updateImage()

    def nextImage(self):
        if len(self.allImages) == 0:
            return
        self.index = (self.index + 1) % len(self.allImages)
        self.openImage()
        
    def previousImage(self):
        if len(self.allImages) == 0:
            return
        self.index = (self.index - 1) % len(self.allImages)
        self.openImage()

    def updateImage(self):
        if len(self.allImages) == 0:
            return
        self.index = self.index if self.index < len(self.allImages) else 0
        self.openImage()   

    def on_tag_click(self,button,tag):
        if not self.filename:
            return

        tags = getTags(self.filename)
        if button.get_active():
            tags.add(tag)
            if self.lockTags:
                self.lockTagsList.add(tag)
        elif tag in tag:
            tags.remove(tag)
            if self.lockTags and tag in self.lockTagsList:
                self.lockTagsList.remove(tag)
        else:
            return

        # Save to file
        setTags(self.filename,tags)

    def on_save_new_tag(self,widget):
        s = self.entryNewTag.get_text()
        self.entryNewTag.set_text("")
        if len(s) == 0 or not self.filename:
            return
        
        tags = getTags(self.filename)
        tags.add(s)
        if self.lockTags:
            self.lockTagsList.add(s)
                
        # Save to file
        setTags(self.filename,tags)
        
        if not s in self.allTags:
            self.allTags = sorted(self.allTags+[s])
            self.showAllTags()

    def on_forward(self,widget):
        self.nextImage()

    def on_back(self,widget):
        self.previousImage()    

    def on_delete(self,widget):
        if self.filename is None:
            return

        send2trash(self.filename)
        del self.allImages[self.index]
        self.updateImage()

    def on_search(self,entry,something):
        s = entry.get_text()
        if len(s) > 2 or len(s) == 0:
            self.search(s)

    def on_sort_by(self,entry):
        self.sort(debug.sortby_store[entry.get_active()][0])

    def on_open_file_chooser(self,widget):
        self.filechooserdialog.show()
        self.filechooserdialog.grab_focus()
        self.entryCurrentPath.set_text(self.directory)
        self.filechooserdialog.set_current_folder(self.directory)

    def on_close_file_chooser(self,widget):
        self.filechooserdialog.hide()

    def on_file_selection_changed(self,filechooser):
        filename = filechooser.get_filename()
        if filename:
            self.entryCurrentPath.set_text(filename)
    
    def on_open_new_path(self,widget):
        self.directory = self.entryCurrentPath.get_text()
        self.filechooserdialog.hide()
        self.loadDirectory()

    def on_key_press(self,widget,ev):
        if isinstance(debug.window.get_focus(),gi.repository.Gtk.Entry):
            return # Ignore key press, if an Entry is currently focused
        
        key = Gdk.keyval_name(ev.keyval)
        if key == 'Left':
            self.previousImage()
            widget.emit_stop_by_name("key-press-event")
            return True
        elif key == 'Right':
            self.nextImage()
            widget.emit_stop_by_name("key-press-event")   
            return True
        elif key == 'space':
            self.keyShortcuts.reset()
            return True
        elif len(key) == 1:
            self.keyShortcuts.add(key)
            return True
        

    def resizeImage(self, w, h):
        # Resize the image
        if not self.pixbuf:
            return
        
        pixbuf = self.pixbuf.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
        self.image.set_from_pixbuf(pixbuf)

    def on_check_resize(self, window=None, force=False):
        # Check whether a resize is possible/needed
        boxAllocation = self.box.get_allocation()
        if not force and self.lastResize and self.lastResize[0] == boxAllocation.width and self.lastResize[1] == boxAllocation.height:
            return

        h = self.image_height
        w = self.image_width

        if h > boxAllocation.height:
            scale = boxAllocation.height / h
            w *= scale
            h *= scale

        if w > boxAllocation.width:
            scale = boxAllocation.width / w
            w *= scale
            h *= scale
            
        self.resizeImage(w,h)
        self.lastResize = [boxAllocation.width,boxAllocation.height]

    def on_open_in_browser(self, widget):
        if self.filename:
            subprocess.Popen(r'explorer /select,"%s"' % self.filename)
            
    def on_check_lock(self, widget):
        state = self.lockTags = self.checkLockButton.get_active()
        if not state:
            self.lockTagsList = set()
            if self.filename:
              self.showSelectedTags(getTags(self.filename))


            
def findImages(path):
    images = []
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.lower().endswith('.jpg'):
                images.append(os.path.join(root, file))
    return images


def openDirectory(path="."):
    path = os.path.abspath(path)

    # Hash
    m = hashlib.md5()
    m.update(path.encode('utf-8'))
    folderhash = m.hexdigest()
    cachefile = "__pycache__/%s.pickle" % folderhash

    # Try to load from cache
    try:
        if os.path.isfile(cachefile):
            when = 0
            with open(cachefile, 'rb') as handle:
                when,_,allTags,allTagsPerImage = pickle.load(handle)
            if time.time() - when < 60*60*24:
                # Use Cache
                images = findImages(path)
                return images,allTags,allTagsPerImage
    except:
        if os.path.isfile(cachefile):
            os.remove(cachefile)

    
    # Find all images
    images = findImages(path)

    # All tags
    allTagsPerImage = {}
    allTags = set();
    couldNotOpen = []
    for img in images:
        try:
            tags = getTags(img)
            allTagsPerImage[img] = tags
            allTags.update(tags)
        except e:
            couldNotOpen.append(img)
            

    for img in couldNotOpen:
        print("Could not open: "+img)
        images.remove(img)
            



    # Cache it
    with open(cachefile, 'wb') as handle:
        pickle.dump([time.time(),images,allTags,allTagsPerImage], handle)

    return images,allTags,allTagsPerImage


debug = False
def main():
    global debug

    directory = "."
    if len(sys.argv) > 1:
        try:
            if os.path.isfile(directory):
                if not os.path.isdir(directory):
                    os.path.dirname(directory)
            else:
                print(sys.argv[1]+" is not valid file/folder")
                directory = "."
                
        except:
            print (sys.argv[1]+" is not valid path")
            directory = "."
    directory = os.path.abspath(directory)
    
    # worker thread/periodic worker:
    # http://faq.pygtk.org/index.py?req=show&file=faq23.037.htp
    # http://faq.pygtk.org/index.py?req=show&file=faq20.012.htp
    
    GObject.threads_init()
    win = ButtonWindow("design.glade",directory)
    debug = win
    win.window.show_all()
    Gdk.threads_enter()
    Gtk.main()
    Gdk.threads_leave()
    saveToFile(force=True)

if __name__ == "__main__":
    sys.exit(main())

