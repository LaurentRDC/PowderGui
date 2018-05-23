# -*- coding: utf-8 -*-
"""
Dialog for processing between AbstractRawDataset and DiffractionDataset
"""
from os import cpu_count
import pyqtgraph as pg
from PyQt5 import QtCore, QtWidgets, QtGui
import numpy as np

fletcher32_help = """ Adds a checksum to each chunk to detect data corruption. 
Attempts to read corrupted chunks will fail with an error. 
No significant speed penalty """.replace('\n', '')

shuffle_help = """ Block-oriented compressors like GZIP or LZF work better 
when presented with runs of similar values. Enabling the 
shuffle filter rearranges the bytes in the chunk and may 
improve compression ratio. """.replace('\n', '')

alignment_help = """If checked, diffraction patterns will be aligned 
using masked normalized cross-correlation. 
This can double the processing time. """ .replace('\n', '')

normalization_help = """If checked, diffraction patterns are normalized so that the total
 intensity is equal for each picture at the same scan. For this to be effective, a good mask 
must be provided. """ .replace('\n', '')

exclude_scans_help = """ Specify scans to exclude comma separated,
e.g. 3,4, 5, 10, 32. """ .replace('\n', '')

DTYPE_NAMES = {'Auto': None,
               '64-bit floats': np.float64,
               '32-bit floats': np.float32,
               '16-bit floats': np.float16,
               '64-bit integers': np.int64,
               '32-bit integers': np.int32,
               '16-bit integers': np.int16}

class MaskCreator(QtWidgets.QWidget):
    """ Widget allowing for creation of arbitrary masks """
    def __init__(self, image, **kwargs):
        super().__init__(**kwargs)

        self.resolution = np.array(image.shape)

        self.rect_masks = list() # list of pg.ROI objects
        self.circ_masks = list()

        self.viewer = pg.ImageView(parent = self)
        self.viewer.setImage(image)
        self.viewer.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding,
                                  QtWidgets.QSizePolicy.MinimumExpanding)

        add_rect_mask_btn = QtWidgets.QPushButton('Add rectangular mask', self)
        add_rect_mask_btn.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        add_rect_mask_btn.clicked.connect(self.add_rect_mask)

        add_circ_mask_btn = QtWidgets.QPushButton('Add circular mask', self)
        add_circ_mask_btn.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        add_circ_mask_btn.clicked.connect(self.add_circ_mask)

        preview_mask_btn = QtWidgets.QPushButton('Preview mask', self)
        preview_mask_btn.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        preview_mask_btn.clicked.connect(self.show_preview_mask)

        clear_masks_btn = QtWidgets.QPushButton('Clear all masks', self)
        clear_masks_btn.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        clear_masks_btn.clicked.connect(self.clear_masks)

        btns = QtWidgets.QHBoxLayout()
        btns.addWidget(add_circ_mask_btn)
        btns.addWidget(add_rect_mask_btn)
        btns.addWidget(preview_mask_btn)
        btns.addWidget(clear_masks_btn)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(btns)
        layout.addWidget(self.viewer)
        self.setLayout(layout)

    @QtCore.pyqtSlot()
    def add_rect_mask(self):
        new_roi = pg.RectROI(pos = self.resolution / 2, size = self.resolution / 10, pen = pg.mkPen('r', width = 4))
        new_roi.addScaleHandle([1, 1], [0, 0])
        new_roi.addScaleHandle([0, 0], [1, 1])
        self.viewer.addItem(new_roi)
        self.rect_masks.append(new_roi)
    
    @QtCore.pyqtSlot()
    def add_circ_mask(self):
        new_roi = pg.CircleROI(pos = self.resolution / 2, size = self.resolution / 10, pen = pg.mkPen('r', width = 4))
        self.viewer.addItem(new_roi)
        self.circ_masks.append(new_roi)
    
    @QtCore.pyqtSlot()
    def show_preview_mask(self):
        image = np.array(self.viewer.image)
        mask = self.composite_mask()
        image[mask] = 0.0

        dialog = QtWidgets.QDialog(parent = self)
        dialog.setWindowTitle('Mask preview')
        dialog.setModal(True)

        view_widget = pg.ImageView(parent = dialog)
        view_widget.setImage(image)

        return dialog.exec_()
    
    @QtCore.pyqtSlot()
    def clear_masks(self):
        for roi in (self.rect_masks + self.circ_masks):
            self.viewer.removeItem(roi)
        self.rect_masks.clear()
        self.circ_masks.clear()
    
    def composite_mask(self):
        """ Returns composite mask where invalid pixels are marked as True """
        # Initially, all pixels are valid
        mask = np.zeros(self.resolution, dtype = np.bool)

        if len(self.circ_masks + self.rect_masks) == 0:
            return mask 

        # No need to compute xx, yy, and rr if there are no
        # circular masks, hence the check for empty list
        if self.circ_masks:
            xx, yy = np.meshgrid(np.arange(0, mask.shape[0]), 
                                 np.arange(0, mask.shape[1]))
            rr = np.empty_like(xx)

            for circ_mask in self.circ_masks:            
                radius = circ_mask.size().x()/2
                corner_x, corner_y = circ_mask.pos().x(), circ_mask.pos().y()
                xc, yc = (round(corner_y + radius), round(corner_x + radius)) #Flip output since image viewer plots transpose...
                rr = np.hypot(xx - xc, yy - yc)
                mask[rr <= radius] = 1

        for rect_mask in self.rect_masks:
            (x_slice, y_slice), _ = rect_mask.getArraySlice(data = mask, img = self.viewer.getImageItem())
            mask[x_slice, y_slice] = True
        
        return mask

class ProcessingDialog(QtWidgets.QDialog):
    """
    Modal dialog used to select dataset processing options.
    """
    processing_parameters_signal = QtCore.pyqtSignal(dict)
    error_message_signal         = QtCore.pyqtSignal(str)

    def __init__(self, raw, **kwargs):
        """
        Parameters
        ----------
        raw : AbstractRawDataset instance
        """
        super().__init__(**kwargs)
        self.setModal(True)
        self.setWindowTitle('Diffraction Dataset Processing')

        self.error_message_signal.connect(self.show_error_message)

        image = raw.raw_data(timedelay = raw.time_points[0], scan = raw.scans[0], bgr = True)
        self.mask_widget = MaskCreator(image, parent = self)

        title = QtWidgets.QLabel('<h2>Data Processing Options<\h2>')
        title.setTextFormat(QtCore.Qt.RichText)
        title.setAlignment(QtCore.Qt.AlignCenter)

        self.processes_widget = QtWidgets.QSpinBox(parent = self)
        self.processes_widget.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        self.processes_widget.setRange(1, cpu_count() - 1)
        self.processes_widget.setValue(min([cpu_count(), 7]))

        self.dtype_widget = QtWidgets.QComboBox(parent = self)
        self.dtype_widget.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        self.dtype_widget.addItems(DTYPE_NAMES.keys())
        self.dtype_widget.setCurrentText('Auto')

        # Set exclude scan widget with a validator
        self.exclude_scans_widget = QtWidgets.QLineEdit(parent = self)
        self.exclude_scans_widget.setPlaceholderText('e.g. 1:5, 6, 7, 10:50, 100')
        self.exclude_scans_widget.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)

        self.alignment_tf_widget = QtWidgets.QCheckBox('Perform alignment (?)', parent = self)
        self.alignment_tf_widget.setToolTip(alignment_help)
        self.alignment_tf_widget.setChecked(False)

        self.normalization_tf_widget = QtWidgets.QCheckBox('Normalize (?)', parent = self)
        self.normalization_tf_widget.setToolTip(normalization_help)
        self.normalization_tf_widget.setChecked(True)

        self.enable_compression_widget = QtWidgets.QCheckBox('Enable compression')
        self.enable_compression_widget.setChecked(False)

        self.lzf_btn = QtWidgets.QRadioButton('LZF', self)
        self.lzf_btn.setChecked(True)

        self.gzip_btn = QtWidgets.QRadioButton('GZIP', self)
        
        filter_btns = QtWidgets.QVBoxLayout()
        filter_btns.addWidget(self.lzf_btn)
        filter_btns.addWidget(self.gzip_btn)

        self.filters = QtWidgets.QGroupBox('Compression filters', parent = self)
        self.filters.setLayout(filter_btns)
        self.filters.setFlat(True)

        self.gzip_level_widget = QtWidgets.QSpinBox(self)
        self.gzip_level_widget.setRange(0, 9)
        self.gzip_level_widget.setValue(4)
        self.gzip_btn.toggled.connect(self.gzip_level_widget.setEnabled)
        self.gzip_level_widget.setEnabled(False)

        self.fletcher32_widget = QtWidgets.QCheckBox('Enable Fletcher32 filter (?)', parent = self)
        self.fletcher32_widget.setToolTip(fletcher32_help)

        self.shuffle_filter_widget = QtWidgets.QCheckBox('Enable shuffle filter (?)', parent = self)
        self.shuffle_filter_widget.setToolTip(shuffle_help)
        self.shuffle_filter_widget.setChecked(True)

        hdf5_params_layout = QtWidgets.QFormLayout()
        hdf5_params_layout.addRow(self.filters)
        hdf5_params_layout.addRow('GZIP level: ', self.gzip_level_widget)
        hdf5_params_layout.addRow(self.fletcher32_widget)
        hdf5_params_layout.addRow(self.shuffle_filter_widget)

        hdf5_params_widget = QtWidgets.QGroupBox(title = 'HDF5 file parameters', parent = self)
        hdf5_params_widget.setLayout(hdf5_params_layout)
        hdf5_params_widget.setEnabled(False)
        self.enable_compression_widget.toggled.connect(hdf5_params_widget.setEnabled)

        hdf5_layout = QtWidgets.QVBoxLayout()
        hdf5_layout.addWidget(self.enable_compression_widget)
        hdf5_layout.addWidget(hdf5_params_widget)

        save_btn = QtWidgets.QPushButton('Launch processing', self)
        save_btn.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        save_btn.clicked.connect(self.accept)

        cancel_btn = QtWidgets.QPushButton('Cancel', self)
        cancel_btn.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setDefault(True)

        # Determine settings
        self.file_dialog = QtWidgets.QFileDialog(parent = self)

        processing_options = QtWidgets.QFormLayout()
        processing_options.addRow('Number of cores:',   self.processes_widget)
        processing_options.addRow('Scans to exclude: ', self.exclude_scans_widget)
        processing_options.addRow('Data type: ',        self.dtype_widget)
        processing_options.addRow(self.alignment_tf_widget)
        processing_options.addRow(self.normalization_tf_widget)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(save_btn)
        buttons.addWidget(cancel_btn)

        params_layout = QtWidgets.QVBoxLayout()
        params_layout.addWidget(title)
        params_layout.addLayout(processing_options)
        params_layout.addLayout(hdf5_layout)
        params_layout.addLayout(buttons)

        params_widget = QtWidgets.QFrame()
        params_widget.setLayout(params_layout)
        params_widget.setFrameShadow(QtWidgets.QFrame.Sunken)
        params_widget.setFrameShape(QtWidgets.QFrame.Panel)

        left_layout = QtWidgets.QVBoxLayout()
        left_layout.addWidget(params_widget)
        left_layout.addStretch()

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.mask_widget)
        layout.addLayout(left_layout)

        self.setLayout(layout)

    @QtCore.pyqtSlot(str)
    def show_error_message(self, msg):
        self.error_dialog = QtGui.QErrorMessage(parent = self)
        self.error_dialog.showMessage(msg)

    def file_params(self):
        """ Returns a dictionary with HDF5 file parameters """
        if not self.enable_compression_widget.isChecked():
            return dict()
        
        compression = 'lzf' if self.lzf_btn.isChecked() else 'gzip'
        fletcher32 = self.fletcher32_widget.isChecked()
        shuffle = self.shuffle_filter_widget.isChecked()
        
        params = {'compression': compression, 
                  'fletcher32': fletcher32, 
                  'shuffle': shuffle}

        if compression == 'gzip':
            params['compression_opts'] = self.gzip_level_widget.value()

        return params

    
    @QtCore.pyqtSlot()
    def accept(self):

        filename = self.file_dialog.getSaveFileName(filter = '*.hdf5')[0]
        if filename == '':
            return

        # Force data type
        dtype = DTYPE_NAMES[self.dtype_widget.currentText()]
        
        exclude_scans_text = self.exclude_scans_widget.text()
        try:
            exclude_scans = parse_range(exclude_scans_text)
        except ValueError:
            self.error_message_signal.emit('Exclude scans unparseable:\n {}'.format(exclude_scans_text))
            return
        
        # The arguments to the iris.processing.process function
        # more arguments will be added by controller
        kwargs = {'filename'     : filename, 
                  'processes'    : self.processes_widget.value(),
                  'exclude_scans': exclude_scans,
                  'dtype'        : dtype,
                  'align'        : self.alignment_tf_widget.isChecked(),
                  'normalize'    : self.normalization_tf_widget.isChecked()}
        
        # Some parameters are from different widgets
        # HDF5 compression kwargs
        kwargs['valid_mask'] = np.logical_not(self.mask_widget.composite_mask())
        kwargs['ckwargs'] = self.file_params()
        
        self.processing_parameters_signal.emit(kwargs)
        super().accept()

def parse_range(range_str):
    """ 
    Parse an integer range into a list of numbers. 
    
    Parameters
    ----------
    range_str : str
        String of the form : "-10, 1:5, 10:50, 100, 101". 
        Ranges are inclusive (the endpoint is included). Can also be
        an empty string.
    
    Returns
    -------
    range : iterable of ints
        Iterable of integers (possibly empty). Guaranteed to be sorted and unique.
    
    Raises
    ------
    ValueError : if the input ``range_str`` is unparseable.
    """
    range_str = str(range_str)
    range_str = range_str.replace(' ','')
    if not range_str:
        return list()

    elements = range_str.split(',')
    if not elements:
        return list()
    
    iterable = list()

    # Two possibilities : ints or ranges
    # Either elem = int
    # or     elem = start:stop
    # Note : stop + 1 because inclusive ranges
    for elem in elements:
        try:
            fl = int(elem)
            iterable.append(fl)
        except ValueError:
            try:
                start, stop = tuple(map(int, elem.split(':')))
                iterable.extend(range(start, stop + 1))
            except:
                # Raise exception from None because full traceback is not useful
                # especially in terms of GUI error messages
                raise ValueError('Unparseable input: ', range_str) from None
    
    return list(sorted(set(iterable)))