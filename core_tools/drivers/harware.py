from dataclasses import dataclass
import qcodes as qc
import numpy as np
import shelve

@dataclass
class virtual_gate:
	name:str
	real_gate_names: list
	virtual_gate_names: list
	virtual_gate_matrix: np.ndarray

	def __init__(self, name, real_gate_names, virtual_gate_names=None):
		'''
		generate a virtual gate object.
		Args:
			real_gate_names (list<str>) : list with the names of real gates
			virtual_gate_names (list<str>) : (optional) names of the virtual gates set. If not provided a "v" is inserted before the gate name.
		'''
		self.name = name
		self.real_gate_names = real_gate_names
		self.virtual_gate_matrix = np.eye(len(real_gate_names)).data
		if virtual_gate_names !=  None:
			self.virtual_gate_names = virtual_gate_names
		else:
			self.virtual_gate_names = []
			for name in real_gate_names:
				self.virtual_gate_names.append("v" + name)

		if len(self.real_gate_names) != len(self.virtual_gate_names):
			raise ValueError("number of real gates and virtual gates is not equal, please fix the input.")

	def __len__(self):
		'''
		get number of gate in the object.
		'''
		return len(self.real_gate_names)

	def __getstate__(self):
		'''
		overwrite state methods so object becomes pickable.
		'''
		state = self.__dict__.copy()
		state["virtual_gate_matrix"] = np.asarray(self.virtual_gate_matrix)
		return state

	def __setstate__(self, new_state):
		'''
		overwrite state methods so object becomes pickable.
		'''
		new_state["virtual_gate_matrix"] = np.asarray(new_state["virtual_gate_matrix"]).data
		self.__dict__.update(new_state)

class virtual_gates_mgr(list):
	def __init__(self, sync_engine, *args):
		super(virtual_gates_mgr, self).__init__(*args)

		self.sync_engine = sync_engine

	def append(self, item):
		if not isinstance(item, virtual_gate):
			raise ValueError("please provide the virtual gates with the virtual_gate data type. {} detected".format(type(item)))

		# check for uniqueness of the virtual gate names.
		virtual_gates = []
		virtual_gates += item.virtual_gate_names
		for i in self:
			virtual_gates += i.virtual_gate_names

		if len(np.unique(np.array(virtual_gates))) != len(virtual_gates):
			raise ValueError("two duplicate names of virtual gates detected. Please fix this.")

		if item.name in list(self.sync_engine.keys()):
			item_in_ram = self.sync_engine[item.name]
			if item_in_ram.real_gate_names == item.real_gate_names:
				np.asarray(item.virtual_gate_matrix)[:] = np.asarray(item_in_ram.virtual_gate_matrix)[:]

		self.sync_engine[item.name] =  item

		return super(virtual_gates_mgr, self).append(item)

	def __getitem__(self, row):
		if isinstance(row, int):
			return super(virtual_gates_mgr, self).__getitem__(row)
		if isinstance(row, str):
			row = self.index(row)
			return super(virtual_gates_mgr, self).__getitem__(row)

		raise ValueError("Invalid key (name) {} provided for the virtual_gate object.")

	def index(self, name):
		i = 0
		options = []
		for v_gate_item in self:
			options.append(v_gate_item.name)
			if v_gate_item.name  == name:
				return i
			i += 1
		if len(options) == 0:
			raise ValueError("Trying to get find a virtual gate matrix, but no matrix is defined.")

		raise ValueError("{} is not defined as a virtual gate. The options are, {}".format(name,options))

class harware_parent(qc.Instrument):
	"""docstring for harware_parent -- init a empy hardware object"""
	def __init__(self, sample_name, storage_location):
		super(harware_parent, self).__init__(sample_name)
		self.storage_location = storage_location
		self.sync = shelve.open(sample_name, flag='c', writeback=True)
		self.dac_gate_map = dict()
		self.boundaries = dict()
		# set this one in the GUI.
		self._AWG_to_dac_conversion = dict()
		if 'AWG2DAC' in list(self.sync.keys()):
			self._AWG_to_dac_conversion = self.sync['AWG2DAC']
		self._virtual_gates = virtual_gates_mgr(self.sync)

	@property
	def virtual_gates(self):
		return self._virtual_gates
	
	@property
	def AWG_to_dac_conversion(self):
		return self._AWG_to_dac_conversion
	
	@AWG_to_dac_conversion.setter
	def AWG_to_dac_conversion(self, AWG_to_dac_ratio):
		if self._AWG_to_dac_conversion.keys() == AWG_to_dac_ratio.keys():
			AWG_to_dac_ratio = self._AWG_to_dac_conversion
		else:
			self._AWG_to_dac_conversion = AWG_to_dac_ratio

	def sync_data(self):
		for item in self.virtual_gates:
			self.sync[item.name] = item
			self.sync['AWG2DAC'] = self._AWG_to_dac_conversion
		self.sync.sync()

if __name__ == '__main__':
	from V2_software.drivers.virtual_gates.examples.hardware_example import hardware_example 
	# example.
	hw = hardware_example("my_harware_example")
	print(hw.virtual_gates)