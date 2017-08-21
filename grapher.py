#!/usr/bin/python

import argparse
import collections
import curses
from curses import textpad
import datetime
import operator
import threading
import time
import sys

DataItem = collections.namedtuple('DataItem', ('time', 'value'))
DataSeries = collections.namedtuple('DataSeries', ('name', 'items'))

# Width of the left hand gutter.
_GUTTER_WIDTH = 10

PARSER = argparse.ArgumentParser(description='TODO')
PARSER.add_argument('file', nargs='*', default='/dev/stdin', help='Input file to read values from')
PARSER.add_argument('--interval', type=float, default=1, help='Interval')


def _get_min_max_values(values):
  max_value = max(values)
  min_value = min(values)
  if max_value == min_value:
    min_value = max_value - 1
  return min_value, max_value


class Graph(object):
  """Graphs a dataset using ncurses.

  Provided dataset should contain a dictionary mapping data series
  names to a list of DataItem.
  """

  def __init__(self, stdscr, data):
    """Initialize a grapher.

    Args:
      stdscr: Reference to ncurses standard screen object.
      data: Dataset to graph.
    """
    self._stdscr = stdscr
    self._data = data
    self.upper_bound = 0

  @property
  def _columns(self):
    _, columns = self._stdscr.getmaxyx()
    return columns - _GUTTER_WIDTH - 3  # 2 for graph borders.

  @property
  def _lines(self):
    lines, _ = self._stdscr.getmaxyx()
    return lines - 2

  def _get_values_in_view(self):
    if self.upper_bound:
      slice_from = max(0, self.upper_bound - self._columns)
      values_in_view = [
          series._replace(items=series.items[slice_from:self.upper_bound])
          for series in self._data
      ]
    else:
      values_in_view = [
          series._replace(items=series.items[-self._columns:])
          for series in self._data
      ]
    return values_in_view

  def _draw_y_axis_labels(self, min_value, max_value):
    lines, _ = self._stdscr.getmaxyx()
    self._stdscr.addstr(0, 0, str(max_value))
    self._stdscr.addstr(lines - 2, 0, str(min_value))

  def _draw_graph_borders(self):
    for line in range(self._lines):
      self._stdscr.addch(line, _GUTTER_WIDTH, curses.ACS_VLINE)
      self._stdscr.addstr(
          line, _GUTTER_WIDTH + 1, '%s' % (' ' * self._columns))
      self._stdscr.addch(
          line, _GUTTER_WIDTH + 1 + self._columns, curses.ACS_VLINE)
    self._stdscr.addch(self._lines, _GUTTER_WIDTH, curses.ACS_LLCORNER)
    for column in xrange(self._columns):
      self._stdscr.addch(curses.ACS_HLINE)
    self._stdscr.addch(curses.ACS_LRCORNER)
    #self._stdscr.addstr( '%s' % ('-' * self._columns))
    
 
  def _draw_x_axis_labels(self, min_datetime, max_datetime):
    lines, columns = self._stdscr.getmaxyx()
    self._stdscr.addstr(lines - 1, _GUTTER_WIDTH, str(min_datetime))
    self._stdscr.addstr(lines - 1, columns - 27, str(max_datetime))
     
  def render(self):
    #if not self._values: return
    self._stdscr.clear()
    values_in_view = self._get_values_in_view()
    if not values_in_view: return
    min_value, max_value = _get_min_max_values(
        [item.value for series in values_in_view for item in series.items])
    
    self._draw_y_axis_labels(min_value, max_value)
    self._draw_x_axis_labels(values_in_view[0].items[0].time,
                             values_in_view[0].items[-1].time)
    self._draw_graph_borders()
    for series in values_in_view:
      self._draw_series_line(series.items, min_value, max_value)

  def _draw_series_line(self, series, min_value, max_value):
    for i, ((time, value), (time, next_value)) in enumerate(zip(
        series, series[1:])):
      line = int(
          (1 - ((value - min_value) / float(max_value - min_value))) *
          (self._lines - 1)
      )
      if next_value is not None:
        next_line = int(
            (1 - ((next_value - min_value) /
             float(max_value - min_value))) *
            (self._lines - 1)
        )
      for j in range(*sorted([line, next_line])):
        self._stdscr.addch(j, _GUTTER_WIDTH + 1 + i, curses.ACS_VLINE)
      if line < next_line:
        self._stdscr.addch(line, _GUTTER_WIDTH + 1 + i, curses.ACS_URCORNER)
        self._stdscr.addch(
            next_line, _GUTTER_WIDTH + 1 + i, curses.ACS_LLCORNER)
      elif line > next_line:
        self._stdscr.addch(line, _GUTTER_WIDTH + 1 + i, curses.ACS_LRCORNER)
        self._stdscr.addch(
            next_line, _GUTTER_WIDTH + 1 + i, curses.ACS_ULCORNER)
      else:
        self._stdscr.addch(line, _GUTTER_WIDTH + 1 + i, curses.ACS_HLINE)
      #for j in range(line, lines - 1):
      #  self._stdscr.addstr(j, _GUTTER_WIDTH + 1 + i, 'x')
    #self._stdscr.addstr(0, 0, str(self._values))
    self._stdscr.refresh()



class InputReader(object):
  
  def __init__(self, input_file_path):
    self._input_file_path = input_file_path

  def get_value(self):
    sys.stderr.write('%s Getting value\n' % time.time())
    sys.stderr.flush()
    with open(self._input_file_path) as input_file:
      value = float(input_file.readline())
      sys.stderr.write('%s Got value %f\n' % (time.time(), value))
      sys.stderr.flush()
      return value


def main_loop(grapher, dataset, interval, stop):
  while not stop.wait(interval):
    for data_series in dataset:
      data_series.items.collect()
    grapher.render()


def handle_user_input(stdscr, grapher):
  keypress = stdscr.getch()
  if keypress == curses.KEY_LEFT:
    if grapher.upper_bound == 0:
      grapher.upper_bound = len(grapher._data[0].items)
    grapher.upper_bound -= 1
  elif keypress == curses.KEY_RIGHT and grapher.upper_bound != 0:
    grapher.upper_bound += 1
    if grapher.upper_bound >= len(grapher._data[0].items):
      grapher.upper_bound = 0
  elif keypress == curses.KEY_HOME:
    grapher.upper_bound = grapher._columns
  elif keypress == curses.KEY_END:
    grapher.upper_bound = 0
  sys.stderr.write('upper bound: %s\n' % grapher.upper_bound)
  grapher.render()


class DataCollector(object):

  def __init__(self, reader):
    self._reader = reader
    self._data = []

  def __getitem__(self, index):
    return self._data[index]

  def __iter__(self):
    return iter(self._data)

  def __len__(self):
    return len(self._data)

  def collect(self):
    try:
      self._data.append(
          DataItem(datetime.datetime.now(), self._reader.get_value()))
    except ValueError:
      pass


def main(stdscr, args):
  curses.curs_set(0)
  dataset = [DataSeries(file_path, DataCollector(InputReader(file_path)))
             for file_path in args.file]
  grapher = Graph(stdscr, dataset) 
  stop = threading.Event()
  thread = threading.Thread(
      target=main_loop, args=(grapher, dataset, args.interval, stop))
  thread.start()
  try:
    while True:
      handle_user_input(stdscr, grapher)
  except KeyboardInterrupt:
    stop.set()
  thread.join()


if __name__ == '__main__':
  curses.wrapper(main, PARSER.parse_args())
