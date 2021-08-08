import random

class Datagetter(object):
  """
  gets one data point at a time
  """
  _dtype = None  # "random" or "thermal"
  _zone = None
  _entered = None
  temp_file_name = None
  temp_file_object = None

  def __init__(self, dtype='random', zone=1):
    self.zone = zone
    self.dtype = dtype

  def __enter__(self):
    self._entered = True
    if self._dtype == 'thermal':
      self.temp_file_object = open(self.temp_file_name, 'r')
    return self

  def __exit__(self, type, value, traceback):
    self._entered = False
    self._close_thermal_file()

  def _close_thermal_file(self):
    try:
      self.temp_file_object.close()
    except Exception as e:
      pass

  def _update_thermal(self):
    self.temp_file_name = f'/sys/class/thermal/thermal_zone{self._zone}/temp'
    if hasattr(self.temp_file_object, 'closed'):
      if self.temp_file_object.closed == False:
        self.temp_file_object.close()
    if self._entered == True:
      self.temp_file_object = open(self.temp_file_name, 'r')

  @property
  def zone(self):
    return self._zone

  @zone.setter
  def zone(self, value):
    if value != self._zone:
      self._zone = value
      self._update_thermal()

  @property
  def dtype(self):
    return self._dtype

  @dtype.setter
  def dtype(self, value):
    if value != self._dtype:
      if value == 'thermal':
        self._dtype = value
        self._update_thermal()
      elif value == 'random':
        self._dtype = value
        self._close_thermal_file()
      else:
        print("Warning: Unknown datatype")

  @property
  def get(self):
    if self._dtype == 'thermal':
      try:
        point_int = int(self.temp_file_object.readline())
        self.temp_file_object.seek(0)
      except:
        point_int = float("nan")
    elif self._dtype == "random":
      point_int = random.randint(0, 100*1000)
    else:
      point_int = 0
    return point_int/1000

  @property
  def thermaltype(self):
    if self._dtype == 'thermal':
      try:
        type_file = f'/sys/class/thermal/thermal_zone{self._zone}/type'
        with open(type_file,'r') as fh:
          type_str = fh.readline()
        result = type_str.strip()
      except Exception as e:
        result = "Unknown"
    elif self._dtype == 'random':
      result = 'Random'
    else:
      result = "None"
    return result

class Downsampler(object):
  """
  Feed this class high frequency data and every [factor]
  samples it will return an average of the last [factor] samples
  Can be used as an input filter to slow down datarate (and potentially increase precision)
  """
  factor = None
  cache = None
  next_sample = None

  def __init__(self, factor = 5):
    self.factor = factor
    self.cache = []
    self.next_sample = 0
    
  def feed(self, sample):
    self.next_sample += 1
    self.cache.append(sample)

    if self.next_sample == self.factor: # the cache is full, compute and return the average
      ret_val = sum(self.cache)/float(self.factor)
      self.next_sample = 0
      self.cache = []
    else:
      ret_val = None

    return ret_val