# ImageTagger
View jpeg images and add tags. Tags are saved in Iptc and Xmp metadata as keywords. Requires Python 3 and Gtk 3.

Tags are saved in both Iptc.Application2.Keywords and Xmp.dc.subject in the JPEG metadata.
The script uses the GExiv2 python API to read and write the Iptc/XMP tags.

The user interface is GTK3 which is available under Windows through [PyGObject](http://pygtk.org).

Tested with/required software:
 * [Python](https://www.python.org/) 3.4
 * GTK 3.0, GExiv2 0.10 (on Windows included in [PyGObject](http://pygtk.org))
 * [Send2Trash 1.3.0](https://pypi.python.org/pypi/Send2Trash)

![screen](https://cloud.githubusercontent.com/assets/8470684/16567940/a4126ca2-4224-11e6-93da-d8d56f152957.jpg)

This software is licensed under GPLv3.