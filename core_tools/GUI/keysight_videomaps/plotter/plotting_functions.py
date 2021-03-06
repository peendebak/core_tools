from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from PyQt5.QtCore import QThread
from PyQt5 import QtCore
import pyqtgraph as pg
import numpy as np
import time
import logging

@dataclass
class plot_widget_data:
    plot_widget: pg.PlotWidget # widget.
    plot_items: list # line in the plot.


class live_plot_abs():
    """
    abstract class that defines some essenstial functions a user should define.
    """
    __metaclass__ = ABCMeta

    @abstractmethod
    def init_plot():
        """
        funtion where the plots are initialized.

        Use:
            self.top_frame (QtWidgets.QFrame) : frame wherin to place the plots
            self.top_layout (QtWidgets.QGridLayout) : layout in the frame for the plots

        # add here data in the self.plot_widgets object (using the data class plot_widget_data)
        """
        raise NotImplemented

    @abstractmethod
    def run():
        '''
        run methods to fetch data. This method will be run in a seperate thread to get data from the digitizer.
        '''
        raise NotImplemented

    @abstractmethod
    def update_plot():
        '''
        update the plot with that data that is in the buffer
        '''
        raise NotImplemented


class live_plot(live_plot_abs, QThread):
    active = False
    plt_finished = True
    update_buffers = False

    _averaging = 1
    _differentiate = False

    # list of plot_widget_data (1 per plot)
    plot_widgets = []
    def __init__(self, app, top_frame, top_layout, parameter_getter, averaging, differentiate):
        '''
        init the class

        app (QApplication) : the QT app that is currently running
        top_frame (QtWidgets.QFrame) : frame wherin to place the plots
        top_layout (QtWidgets.QGridLayout) : layout in the frame for the plots
        parameter_getter (QCoDeS multiparamter) : qCoDeS multiparamter that is used to get the data.
        averaging (int) : number of times the plot needs to be averaged.
        differentiate (bool) : differentiate plot - true/false
        '''
        super(QThread, self).__init__()
        super(live_plot_abs, self).__init__()
        # general variables needed for the plotting
        self.app = app
        self.n_plots = len(parameter_getter.names)
        self.top_frame = top_frame
        self.top_layout = top_layout

        # getter for the scan.
        self.parameter_getter = parameter_getter
        self.shape = parameter_getter.shapes[0] #assume all the shapes are the same.
        self.plot_widgets = []

        # plot properties
        self._averaging = averaging
        self._differentiate = differentiate

        # generate the buffers needed for the plotting and construct the plots.
        self.generate_buffers()
        self.init_plot()

        # make a updater to plot periodically plot what is in the buffer.
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plot)


    @property
    def averaging(self):
        return self._averaging

    @averaging.setter
    def averaging(self, value):
        self._averaging = value
        if self._averaging < 1:
            self._averaging = 1

        self.update_buffers = True

    @property
    def differentiate(self):
        return self._differentiate

    @differentiate.setter
    def differentiate(self, value):
        self._differentiate = value
        self.update_buffers = True

    def generate_buffers(self):
        # buffer_data
        shape = list(self.shape)

        self.buffer_data = []
        self.plot_data = []

        for i in range(self.n_plots):
            self.buffer_data.append(np.zeros([self._averaging, *shape]))
            self.plot_data.append(np.zeros([*shape]))

    def start(self):
        logging.info('running start function in plotting_func')
        self.active = True
        self.plt_finished = False
        self.timer.start(0.2)

        super(live_plot, self).start()

    def stop(self):
        self.active = False
        self.timer.stop()

        while self.plt_finished != True:
            time.sleep(0.01) #5ms interval to make sure gil releases.


    def remove(self):
        self.timer.stop()
        self.timer.deleteLater()
        self.timer = None

        for plot in self.plot_widgets:
            self.top_layout.removeWidget(plot.plot_widget)
            plot.plot_widget.clear()
            plot.plot_widget.deleteLater()
            plot.plot_widget = None

        self.plot_widgets = []

class _1D_live_plot(live_plot):
    """1D live plot fuction"""

    def init_plot(self):
        for i in range(self.n_plots):
            plot_1D = pg.PlotWidget()
            plot_1D.showGrid(x=True, y=True)
            plot_1D.setLabel('left', self.parameter_getter.labels[i], self.parameter_getter.units[i])
            plot_1D.setLabel('bottom', self.parameter_getter.setpoint_labels[i][0], self.parameter_getter.setpoint_units[i][0])
            self.top_layout.addWidget(plot_1D, 0, i, 1, 1)

            my_range = self.parameter_getter.setpoints[0][0][-1]
            self.x_data = np.linspace(-my_range, my_range, self.plot_data[i].size)

            curve = plot_1D.plot(self.x_data, self.plot_data[i], pen=(255,0,0))
            plot_data = plot_widget_data(plot_1D, [curve])
            self.plot_widgets.append(plot_data)

    def generate_buffers(self):
        super().generate_buffers()
        my_range = np.abs(self.parameter_getter.setpoints[0][0][-1])
        self.x_data = np.linspace(-my_range, my_range, self.plot_data[0].size)

    def update_plot(self):
        for i in range(len(self.plot_widgets)):
            self.plot_widgets[i].plot_items[0].setData(self.x_data,self.plot_data[i])

    def run(self):
        # fetch data here -- later ported through in update plot. Running update plot from here causes c++ to delethe the curves object for some wierd reason..
        while (self.active == True):
            try:
                input_data = self.parameter_getter.get()

                for i in range(self.n_plots):
                    y = input_data[i]
                    if self.differentiate == True:
                        y = np.diff(y)

                    self.buffer_data[i] = np.roll(self.buffer_data[i],-1,0)
                    if self.update_buffers == True:
                        # kind of hacky place, but it works well. TODO write as try expect clause.
                        self.generate_buffers()
                        self.update_buffers = False
                        y=np.zeros([len(self.plot_data[i])])

                    self.buffer_data[i][-1] = y

                    self.plot_data[i] = np.sum(self.buffer_data[i], 0)/len(self.buffer_data[i])
            except:
                print('frame dropped -- reason unclear ..')

        self.plt_finished = True

class _2D_live_plot(live_plot):
    """function that has as sole pupose generating live plots of a line trace (or mupliple if needed)"""

    def init_plot(self):
        for i in range(self.n_plots):
            plot_2D = pg.PlotWidget()
            img = pg.ImageItem()
            plot_2D.addItem(img)
            plot_2D.setLabel('left', self.parameter_getter.setpoint_labels[i][0], self.parameter_getter.setpoint_units[i][0])
            plot_2D.setLabel('bottom', self.parameter_getter.setpoint_labels[i][1], self.parameter_getter.setpoint_units[i][1])
            self.top_layout.addWidget(plot_2D, 0, i, 1, 1)

            img.translate(-self.parameter_getter.setpoints[0][1][0][-1], -self.parameter_getter.setpoints[0][0][-1])
            img.scale(1/self.shape[0]*self.parameter_getter.setpoints[0][1][0][-1]*2, 1/self.shape[1]*self.parameter_getter.setpoints[0][0][-1]*2)

            plot_data = plot_widget_data(plot_2D, [img])
            self.plot_widgets.append(plot_data)

    def update_plot(self):
        for i in range(len(self.plot_widgets)):
            self.plot_widgets[i].plot_items[0].setImage(self.plot_data[i])
            if self.active == False:
                break


    def run(self):
        # fetch data here -- later ported through in update plot. Running update plot from here causes c++ to delethe the curves object for some wierd reason..
        while (self.active == True):
            try:
                input_data = self.parameter_getter.get()
                for i in range(self.n_plots):
                    xy = input_data[i][:, :].T

                    if self.differentiate == True:
                        grad = np.gradient(xy)
                        xy = np.sqrt(grad[0]**2 + grad[1]**2)

                    self.buffer_data[i] = np.roll(self.buffer_data[i],-1,0)
                    if self.update_buffers == True:
                        # kind of hacky place, but it works well. TODO write as try expect clause.
                        self.generate_buffers()
                        self.update_buffers = False
                        xy=np.zeros(self.plot_data[0].shape)

                    self.buffer_data[i][-1] = xy
                    self.plot_data[i] = np.sum(self.buffer_data[i], 0)/len(self.buffer_data[i])
            except Exception as e:
                logging.error(f'Exception: {e}')#, exc_info=True)

        self.plt_finished = True


if __name__ == '__main__':
    from test_UI.liveplot_only import Ui_MainWindow
    import matplotlib
    matplotlib.use("Qt5Agg")
    from V2_software.LivePlotting.data_getter.scan_generator_Virtual import construct_1D_scan_fast, construct_2D_scan_fast, fake_digitizer
    from PyQt5 import QtCore, QtGui, QtWidgets
    import sys

    dim = "1D"
    # set graphical user interface
    app = QtWidgets.QApplication([])
    mw = QtWidgets.QMainWindow()
    window = Ui_MainWindow()
    window.setupUi(mw)
    dig = fake_digitizer("fake_digitizer")


    if dim == "1D":
        p = construct_1D_scan_fast(gate = "test", swing = 100, n_pt=700, t_step=5, biasT_corr= False, pulse_lib=None, digitizer=dig)

        plot = _1D_live_plot(app, window.frame_plots, window.grid_plots, p ,1,False)

        def stop_function(*args):
            plot.stop()
            plot.remove()

        plot.start()
        window.Close.clicked.connect(stop_function)

    if dim == "2D":
        p = construct_2D_scan_fast("test", 100, 10, "test2", 150, 10, t_step=5, biasT_corr= False, pulse_lib=None, digitizer=dig)

        plot = _2D_live_plot(app, window.frame_plots, window.grid_plots, p ,1,False)

        def stop_function(*args):
            plot.stop()
            plot.remove()

        plot.start()
        window.Close.clicked.connect(stop_function)


    mw.show()
    sys.exit(app.exec_())



