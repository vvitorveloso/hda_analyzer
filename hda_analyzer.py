#!/usr/bin/env python3
#
# Copyright (c) 2008-2012 by Jaroslav Kysela <perex@perex.cz>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.

"""
hda_analyzer - a tool to analyze HDA codecs widgets and connections

Usage: hda_analyzer [[codec_proc] ...]
   or: hda_analyzer --monitor

    codec_proc might specify multiple codec files per card:
        codec_proc_file1+codec_proc_file2
    or codec_proc might be a dump from alsa-info.sh
    or codec_proc might be a hash for codec database at www.alsa-project.org
    or codec_proc might be a URL for codec dump or alsa-info.sh dump

    Monitor mode: check for codec changes in realtime and dump diffs.
"""

import os
import sys
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Pango

from hda_codec import HDACodec, HDA_card_list, HDA_Exporter_pyscript, \
                      EAPDBTL_BITS, PIN_WIDGET_CONTROL_BITS, \
                      PIN_WIDGET_CONTROL_VREF, DIG1_BITS, GPIO_IDS, \
                      HDA_INPUT, HDA_OUTPUT
from hda_proc import DecodeProcFile, DecodeAlsaInfoFile, HDACodecProc
from hda_guilib import *
from hda_graph import create_graph

def gethttpfile(url, size=1024*1024):
  from urllib.request import urlopen
  with urlopen(f"{URL}/{f}") as response:
    contents = response.read()
  return contents

def read_nodes2(card, codec):
  try:
    c = HDACodec(card, codec)
  except OSError as msg:
    if msg.errno == 13:
      print("Codec %i/%i unavailable - permissions..." % (card, codec))
    elif msg.errno == 16:
      print("Codec %i/%i is busy..." % (card, codec))
    elif msg.errno != 2:
      print("Codec %i/%i access problem (%s)" % repr(msg))
    return
  c.analyze()
  if not card in CODEC_TREE:
    CODEC_TREE[card] = {}
    DIFF_TREE[card] = {}
  CODEC_TREE[card][c.device] = c
  DIFF_TREE[card][c.device] = c.dump()

def read_nodes3(card, codec, proc_file):
  c = HDACodecProc(card, codec, proc_file)
  c.analyze()
  if not card in CODEC_TREE:
    CODEC_TREE[card] = {}
    DIFF_TREE[card] = {}
  CODEC_TREE[card][c.device] = c
  DIFF_TREE[card][c.device] = c.dump()

def read_nodes(proc_files):
  l = HDA_card_list()
  for c in l:
    for i in range(4):
      read_nodes2(c.card, i)
  card = 1000
  for f in proc_files:
    a = f.split('+')
    idx = 0
    if len(a) == 1:
      if a[0].startswith('http://'):
        proc_file = gethttpfile(a[0])
      elif len(a[0]) == 40 and not os.path.exists(a[0]):
        url = 'http://www.alsa-project.org/db/?f=' + a[0]
        print('Downloading contents from %s' % url)
        proc_file = gethttpfile(url)
        if not proc_file:
          print("HASH %s cannot be downloaded..." % a[0])
          continue
        else:
          print('  Success')
      else:
        proc_file = DecodeProcFile(a[0])
      proc_file = DecodeAlsaInfoFile(proc_file)
      for i in proc_file:
        read_nodes3(card, idx, i)
        card += 1
      a = []
    for i in a:
      proc_file = DecodeProcFile(i)
      read_nodes3(card, idx, proc_file)
      idx += 1
    card += 1
  cnt = 0
  for c in CODEC_TREE:
    if len(CODEC_TREE[c]) > 0:
      cnt += 1
  return cnt    

def save_to_file(filename, txt, mode=None):
  try:
    fp = open(filename, "w+")
    fp.write(txt)
    fp.close()
    if mode:
      os.chmod(filename, 0o755)
  except:
    print("Unable to save text to '%s'" % filename)

(
    TITLE_COLUMN,
    CARD_COLUMN,
    CODEC_COLUMN,
    NODE_COLUMN,
    ITALIC_COLUMN
) = range(5)

class HDAAnalyzer(Gtk.Window):
  info_buffer = None
  node_window = None
  codec = None
  node = None

  def __init__(self):
    GObject.GObject.__init__(self)
    self.connect('destroy', self.__destroy)
    self.set_default_size(800, 400)
    self.set_title(self.__class__.__name__)
    self.set_border_width(10)

    hbox = Gtk.HBox(False, 3)
    self.add(hbox)
    
    vbox = Gtk.VBox(False, 0)
    scrolled_window = Gtk.ScrolledWindow()
    scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled_window.set_shadow_type(Gtk.ShadowType.IN)
    treeview = self.__create_treeview()
    treeview.set_size_request(250, 600)
    scrolled_window.add(treeview)
    vbox.pack_start(scrolled_window, True, True, 0)
    hbox1 = Gtk.HBox(False, 0)
    button = Gtk.Button("About")
    button.connect("clicked", self.__about_clicked)
    button.set_tooltip_text("README! Show the purpose of this program.")
    hbox1.pack_start(button, True, True, 0)
    button = Gtk.Button("Revert")
    button.connect("clicked", self.__revert_clicked)
    button.set_tooltip_text("Revert settings for selected codec.")
    hbox1.pack_start(button, True, True, 0)
    button = Gtk.Button("Diff")
    button.connect("clicked", self.__diff_clicked)
    button.set_tooltip_text("Show settings diff for selected codec.")
    hbox1.pack_start(button, True, True, 0)
    button = Gtk.Button("Exp")
    button.connect("clicked", self.__export_clicked)
    button.set_tooltip_text("Export settings differences for selected codec.\nGenerates a python script.")
    hbox1.pack_start(button, True, True, 0)
    button = Gtk.Button("Graph")
    button.connect("clicked", self.__graph_clicked)
    button.set_tooltip_text("Show graph for selected codec.")
    hbox1.pack_start(button, True, True, 0)
    vbox.pack_start(hbox1, False, False,0)
    hbox.pack_start(vbox, False, False,0)
    self.notebook = Gtk.Notebook()
    hbox.pack_start(self.notebook, True, True, 0)
    self.node_window = Gtk.Table()
    self._new_notebook_page(self.node_window, '_Node editor')
    scrolled_window, self.info_buffer = self.__create_text(self.__dump_visibility)
    self._new_notebook_page(scrolled_window, '_Text dump')
    self.show_all()    
    TRACKER.add(self)
     
  def __destroy(self, widget):
    TRACKER.close(self)

  def simple_dialog(self, type, msg):
    dialog = Gtk.MessageDialog(self,
                      Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                      type, Gtk.ButtonsType.OK, msg)
    dialog.run()
    dialog.destroy()

  def __about_clicked(self, button):
    dialog = Gtk.Dialog('About', self,
                        Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                        (Gtk.STOCK_OK, Gtk.ResponseType.OK))
    text_view = Gtk.TextView()
    text_view.set_border_width(4)
    str =  """\
HDA Analyzer

This tool allows change the HDA codec setting using direct hardware access
bypassing driver's mixer layer.

To learn more about HDA (High Definition Audio), see
http://www.intel.com/standards/hdaudio/ for more details.

Please, if you find how your codec work, send this information to alsa-devel
mailing list - http://www.alsa-project.org .

Bugs, ideas, comments about this program should be sent to alsa-devel
mailing list, too.
"""
    buffer = Gtk.TextBuffer()
    iter = buffer.get_iter_at_offset(0)
    buffer.insert(iter, str[:-1])
    text_view.set_buffer(buffer)
    text_view.set_editable(False)
    text_view.set_cursor_visible(False)
    dialog.vbox.pack_start(text_view, False, False,0)
    dialog.show_all()
    dialog.run()
    dialog.destroy()
    
  def __revert_clicked(self, button):
    if not self.codec:
      msg = "Please, select a codec in left codec/node tree."
      type = Gtk.MessageType.WARNING
    else:
      self.codec.revert()
      self.__refresh()
      msg = "Setting for codec %s/%s (%s) was reverted!" % (self.codec.card, self.codec.device, self.codec.name)
      type = Gtk.MessageType.INFO

    self.simple_dialog(type, msg)

  def __diff_clicked(self, button):
    if not self.codec:
      self.simple_dialog(Gtk.MessageType.WARNING, "Please, select a codec in left codec/node tree.")
      return
    dialog = Gtk.Dialog('Diff', self,
                        Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                        (Gtk.STOCK_OK, Gtk.ResponseType.OK))
    text_view = Gtk.TextView()
    text_view.set_border_width(4)
    fontName = get_fixed_font()
    text_view.modify_font(fontName)
    str = do_diff1(self.codec, DIFF_TREE[self.card][self.codec.device])
    if str == '':
      str = 'No changes'
    buffer = Gtk.TextBuffer()
    iter = buffer.get_iter_at_offset(0)
    buffer.insert(iter, str[:-1])
    text_view.set_buffer(buffer)
    text_view.set_editable(False)
    text_view.set_cursor_visible(False)
    dialog.vbox.pack_start(text_view, False, False,0)
    dialog.show_all()
    dialog.run()
    dialog.destroy()
    
  def __export_clicked(self, button):
    if not self.codec:
      self.simple_dialog(Gtk.MessageType.WARNING, "Please, select a codec in left codec/node tree.")
      return
    exporter = HDA_Exporter_pyscript()
    self.codec.export(exporter)
    dialog = Gtk.Dialog(exporter.title(), self,
                        Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
                        (Gtk.STOCK_OK, Gtk.ResponseType.OK,
                         Gtk.STOCK_SAVE_AS, Gtk.ResponseType.YES))
    text_view = Gtk.TextView()
    text_view.set_border_width(4)
    fontName = get_fixed_font()
    text_view.modify_font(fontName)
    str = exporter.text(self.codec)
    buffer = Gtk.TextBuffer()
    iter = buffer.get_iter_at_offset(0)
    buffer.insert(iter, str[:-1])
    text_view.set_buffer(buffer)
    text_view.set_editable(False)
    text_view.set_cursor_visible(False)
    dialog.vbox.pack_start(text_view, False, False,0)
    dialog.show_all()
    r = dialog.run()
    dialog.destroy()
    if r == Gtk.ResponseType.YES:
      sdialog = Gtk.FileChooserDialog('Save %s as...' % exporter.stitle(),
                    self, Gtk.FileChooserAction.SAVE,
                     (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                      Gtk.STOCK_SAVE, Gtk.ResponseType.OK))
      sdialog.set_default_response(Gtk.ResponseType.OK)

      filter = Gtk.FileFilter()
      filter.set_name("Python Scripts")
      filter.add_mime_type("text/x-python")
      filter.add_mime_type("text/x-python-script")
      filter.add_pattern("*.py")
      sdialog.add_filter(filter)

      filter = Gtk.FileFilter()
      filter.set_name("All files")
      filter.add_pattern("*")
      sdialog.add_filter(filter)

      sr = sdialog.run()
      if sr == Gtk.ResponseType.OK:
        save_to_file(sdialog.get_filename(), str, 0o755)
      sdialog.destroy()
    
  def __graph_clicked(self, button):
    if not self.codec:
      self.simple_dialog(Gtk.MessageType.WARNING, "Please, select a codec in left codec/node tree.")
      return
    create_graph(self.codec)
    
  def __refresh(self):
    self.load()
    self.__dump_visibility(None, None)

  def __dump_visibility(self, textview, event):
    codec = self.codec
    node = self.node
    if not codec:
      txt = 'Show some card info here...'
    elif codec and self.node < 0:
      txt = codec.dump(skip_nodes=True)
    else:
      n = codec.get_node(node)
      txt = codec.dump_node(n)
    buffer = self.info_buffer
    start, end = buffer.get_bounds()
    buffer.delete(start, end)
    if not txt: return
    iter = buffer.get_iter_at_offset(0)
    buffer.insert(iter, txt)

  def selection_changed_cb(self, selection):
    model, iter = selection.get_selected()
    if not iter:
      return False
    card = model.get_value(iter, CARD_COLUMN)
    codec = model.get_value(iter, CODEC_COLUMN)
    node = model.get_value(iter, NODE_COLUMN)
    self.card = card
    self.codec = None
    if codec >= 0:
      self.codec = CODEC_TREE[card][codec]
    self.node = node
    self.__refresh()

  def load(self):
    codec = self.codec
    node = self.node
    n = None    
    if not codec:
      txt = 'Show some card info here...'
    elif codec and node < 0:
      txt = codec.dump(skip_nodes=True)
    else:
      n = codec.get_node(node)

    for child in self.node_window.get_children()[:]:
      self.node_window.remove(child)
      child.destroy()

    if not n:
      if not codec:
        for i in CODEC_TREE[self.card]:
          card = CODEC_TREE[self.card][i].mcard
          break
        self.node_window.add(NodeGui(card=card))
      elif codec:
        self.node_window.add(NodeGui(codec=codec))
      else:
        return
    else:
      self.node_window.add(NodeGui(node=n))
    self.node_window.show_all()

  def _new_notebook_page(self, widget, label):
    l = Gtk.Label(label='')
    l.set_text_with_mnemonic(label)
    self.notebook.append_page(widget, l)
  
  def __create_treeview(self):
    model = Gtk.TreeStore(
      GObject.TYPE_STRING,
      GObject.TYPE_INT,
      GObject.TYPE_INT,
      GObject.TYPE_INT,
      GObject.TYPE_BOOLEAN
    )
   
    treeview = Gtk.TreeView(model)
    selection = treeview.get_selection()
    selection.set_mode(Gtk.SelectionMode.BROWSE)
    treeview.set_size_request(200, -1)

    for card in CODEC_TREE:
      iter = model.append(None)
      model.set(iter,
                  TITLE_COLUMN, 'card-%s' % card,
                  CARD_COLUMN, card,
                  CODEC_COLUMN, -1,
                  NODE_COLUMN, -1,
                  ITALIC_COLUMN, False)
      for codec in CODEC_TREE[card]:
        citer = model.append(iter)
        codec = CODEC_TREE[card][codec]
        model.set(citer,
                    TITLE_COLUMN, 'codec-%s' % codec.device,
                    CARD_COLUMN, card,
                    CODEC_COLUMN, codec.device,
                    NODE_COLUMN, -1,
                    ITALIC_COLUMN, False)
        for nid in codec.nodes:
          viter = model.append(citer)
          node = codec.get_node(nid)
          model.set(viter,
                      TITLE_COLUMN, 'Node[0x%02x] %s' % (nid, node.wtype_id),
                      CARD_COLUMN, card,
                      CODEC_COLUMN, codec.device,
                      NODE_COLUMN, nid,
                      ITALIC_COLUMN, False)
          nid += 1
  
    cell = Gtk.CellRendererText()
    cell.set_property('style', Pango.Style.ITALIC)
  
    column = Gtk.TreeViewColumn('Nodes', cell, text=TITLE_COLUMN,
                                style_set=ITALIC_COLUMN)
  
    treeview.append_column(column)

    selection.connect('changed', self.selection_changed_cb)
    
    treeview.expand_all()
    return treeview

  def __create_text(self, callback):
    scrolled_window = Gtk.ScrolledWindow()
    scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scrolled_window.set_shadow_type(Gtk.ShadowType.IN)
    
    text_view = Gtk.TextView()
    fontName = get_fixed_font()
    text_view.modify_font(fontName)
    scrolled_window.add(text_view)
    
    buffer = Gtk.TextBuffer()
    text_view.set_buffer(buffer)
    text_view.set_editable(False)
    text_view.set_cursor_visible(False)
    text_view.connect("visibility-notify-event", callback)
    
    text_view.set_wrap_mode(True)
    
    return scrolled_window, buffer

def monitor():
  from time import sleep
  print("Watching %s cards" % len(CODEC_TREE))
  dumps = {}
  while 1:
    ok = False
    for card in CODEC_TREE:
      if not card in dumps:
        dumps[card] = {}
      for codec in CODEC_TREE[card]:
        if not codec in dumps[card]:
          dumps[card][codec] = ''
        c = CODEC_TREE[card][codec]
        if c.hwaccess:
          ok = True
        c.reread()
        diff = ''
        dump1 = c.dump()
        if dumps[card][codec]:
          diff = do_diff1(c, dumps[card][codec])
        dumps[card][codec] = dump1
        if diff:
          print("======================================")
          print(diff)
    if not ok:
      print("Nothing to monitor (no hwdep access)")
      break
    sleep(1)

def main(argv):
  cmd = None
  if len(argv) > 1 and argv[1] in ('-h', '-help', '--help'):
    print(__doc__ % globals())
    return 0
  if len(argv) > 1 and argv[1] in ('-m', '-monitor', '--monitor'):
    cmd = 'monitor'
    del argv[1]
  if len(argv) > 1 and argv[1] in ('-g', '-graph', '--graph'):
    cmd = 'graph'
    del argv[1]
  if read_nodes(sys.argv[1:]) == 0:
    print("No HDA codecs were found or insufficient priviledges for ")
    print("/dev/snd/controlC* and /dev/snd/hwdepC*D* device files.")
    print()
    print("You may also check, if you compiled HDA driver with HWDEP")
    print("interface as well or close all application using HWDEP.")
    print()
    print("Try run this program as root user.")
    return 0
  else:
    if cmd == 'monitor':
      monitor()
      return 1
    if cmd == 'graph':
      for card in CODEC_TREE:
        for codec in CODEC_TREE:
          create_graph(CODEC_TREE[card][codec])
    else:
      HDAAnalyzer()
    Gtk.main()
  return 1

if __name__ == '__main__':
  sys.exit(main(sys.argv))
