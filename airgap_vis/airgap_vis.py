from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.PyQt.QtWidgets import *
from qgis.core import *

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .airgap_vis_dialog import AirGapVisDialog
from .simulated_visualization import SimVisDialog
import os.path
from PIL import Image, ImageQt, ImageEnhance

import laspy
import numpy
import os
import sys

from .airgap import *

POINT_TYPE = QgsWkbTypes.PointGeometry
LINE_TYPE = QgsWkbTypes.LineGeometry

def lm(message):
    QgsMessageLog.logMessage(str(message))

def info(message):
    QMessageBox.information(None, "", str(message))

def warning(message):
    QMessageBox.warning(None, "", str(message))

class AirGapVis:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'AirGapVis_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr(u'&AirGapVis')

        self.first_start = None

        self.point_clouds = []
        self.vector_layers = []
        self.raster_layers = []

        self.contour_path = None
        self.depth_path = None
        self.background_path = {
            Direction.EAST_TO_WEST.value: None,
            Direction.WEST_TO_EAST.value: None
        }
        self.west_east_background_path = None
        self.east_west_background_path = None

        self.width = None
        self.minimum_height = None
        self.padding_left = None
        self.padding_right = None
        self.padding_bottom = None
        self.refine_ends = None
        self.direction = Direction.WEST_TO_EAST

        self.enhancement_steps = 10

        self.adjustments = {
            Direction.EAST_TO_WEST.value: {
                "brightness": 1,
                "contrast": 1,
                "saturation": 1,
                "sharpness": 0
            },
            Direction.WEST_TO_EAST.value: {
                "brightness": 1,
                "contrast": 1,
                "saturation": 1,
                "sharpness": 0
            },
        }

        self.images = {
            Direction.EAST_TO_WEST.value: {
                "original": None,
                "enhanced": None,
            },
            Direction.WEST_TO_EAST.value: {
                "original": None,
                "enhanced": None,
            }
        }

        self.imageLabels = {
            Direction.EAST_TO_WEST.value: None,
            Direction.WEST_TO_EAST.value: None
        }

    def tr(self, message):
        return QCoreApplication.translate('AirGapVis', message)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        icon_path = ':/plugins/airgap_vis/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Airgap Vis'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True


    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&AirGapVis'),
                action)
            self.iface.removeToolBarIcon(action)

    def select_contour_file(self):
        filename, file_filter = QFileDialog.getSaveFileName(self.dlg, "Select Contour File Name")

        if filename:
            if not filename.endswith(".json") and not filename.endswith(".geojson"):
                filename += ".json"
            self.dlg.contourLineEdit.setText(filename)

    def select_depth_file(self):
        filename, file_filter = QFileDialog.getSaveFileName(self.dlg, "Select Depth File Name")

        if filename:
            if not filename.endswith(".json") and not filename.endswith(".geojson"):
                filename += ".json"
            self.dlg.depthLineEdit.setText(filename)

    def select_east_west_background_file(self):
        filename, file_filter = QFileDialog.getSaveFileName(self.dlg, "Select East to West Background Image File Name")

        if filename:
            if not filename.endswith(".png"):
                filename += ".png"
            self.dlg.eastWestBackgroundLineEdit.setText(filename)

    def select_west_east_background_file(self):
        filename, file_filter = QFileDialog.getSaveFileName(self.dlg, "Select West to East Background Image File Name")

        if filename:
            if not filename.endswith(".png"):
                filename += ".png"
            self.dlg.westEastBackgroundLineEdit.setText(filename)

    def bathymetry_changed(self, index):
        if index < len(self.raster_layers):
            bathymetry_layer = self.raster_layers[index]
            band_count = bathymetry_layer.layer().bandCount()
            self.dlg.bandSpinBox.setMaximum(band_count)

            if band_count == 1:
                self.dlg.bandLabel.hide()
                self.dlg.bandSpinBox.hide()
            else:
                self.dlg.bandLabel.show()
                self.dlg.bandSpinBox.show()

    def create_depth_file_changed(self):
        if self.dlg.createDepthFileCheckBox.isChecked():
            self.dlg.bathymetryComboBox.setEnabled(True)
        else:
            self.dlg.bathymetryComboBox.setEnabled(False)

    def determine_end_points(self, point_cloud, vector_layer):
        point_cloud_bounds = point_cloud.layer().dataProvider().polygonBounds()
        
        points = []

        for feature in vector_layer.layer().getFeatures():
            geometry = feature.geometry()

            if geometry.type() == POINT_TYPE and QgsWkbTypes.isSingleType(geometry.wkbType()):
                point = geometry.asPoint()
                if point_cloud_bounds.intersects(geometry):
                    points.append(point)

        if len(points) > 2:
            return [], "Unable to determine end points. Too many points within point cloud bounds."
        elif len(points) < 2:
            return {}, f"Unable to determine end points. Not enough points within point cloud bounds."
        else:
            if points[0].x() > points[1].x():
                return [[points[1].x(), points[1].y()],[points[0].x(),points[0].y()]], None
            else:
                return [[points[0].x(), points[0].y()],[points[1].x(),points[1].y()]], None

    def color_image(self, point_cloud, image, scale, padding_left, padding_right, padding_bottom, direction):
        pixmap = QPixmap(image.width(), image.height())
        pixmap.fill(Qt.white)
        
        painter = QPainter(pixmap)
        painter.drawImage(0,0,image)

        if self.sim_vis.waterCheckBox.isChecked():
            painter.fillRect(0, image.height() - padding_bottom, image.width(), padding_bottom, 
                QColor.fromRgbF(0,0.52,0.79,0.75))

        y = image.height() - padding_bottom

        if direction != self.direction:
            depths = point_cloud.depths.copy()
            depths.reverse()
            contour = point_cloud.contour.copy()
            contour.reverse()
        else:
            depths = point_cloud.depths
            contour = point_cloud.contour

        if self.sim_vis.bathymetryCheckBox.isChecked():
            for i in range(len(depths)):
                depth_height = int(abs(depths[i])/scale)
                painter.fillRect(i, y + depth_height, 1, padding_bottom - depth_height, QColor.fromRgbF(0,0,0,0.75))

        if self.sim_vis.vesselHeightSpinBox.value() > 0:
            previous_contour_height = 0

            x = padding_left
            for i in range(len(contour)):
                contour_meters = contour[i][2]
                contour_height = int(contour[i][2]/scale)
    
                if contour_height > 0: 
                    if self.sim_vis.vesselHeightSpinBox.value() < contour_meters:
                        painter.fillRect(x+i, y - contour_height, 1, contour_height, QColor.fromRgbF(0,1,0,0.75))
                    else:
                        painter.fillRect(x+i, y - contour_height, 1, contour_height, QColor.fromRgbF(1,0,0,0.75))
                    previous_contour_height = contour_height
                else:
                    painter.fillRect(x+i, y - previous_contour_height, 1, previous_contour_height, QColor.fromRgbF(1,0,0,0.75))

        painter.end()

        return pixmap

    def adjustment_changed(self, value, adjustment):
        direction = self.sim_vis.sender().parentWidget().direction
        self.adjustments[direction.value][adjustment] = value / self.enhancement_steps
        self.enhance_image(direction)
        self.update_simulated_visualization(direction)

    def brightness_changed(self, value):
        self.adjustment_changed(value, "brightness")

    def contrast_changed(self, value):
        self.adjustment_changed(value, "contrast")

    def saturation_changed(self, value):
        self.adjustment_changed(value, "saturation")

    def sharpness_changed(self, value):
        self.adjustment_changed(value, "sharpness")

    def visualization_option_changed(self, value):
        self.update_simulated_visualization(Direction.EAST_TO_WEST)
        self.update_simulated_visualization(Direction.WEST_TO_EAST)

    def enhance_image(self, direction):
        original_image = self.images[direction.value]["original"]
        adjustments = self.adjustments[direction.value]

        width = original_image.width()
        height = original_image.height()

        image = original_image.convertToFormat(QImage.Format.Format_RGBA8888)
        image_data = image.bits()
        image_data.setsize(height*width*4)

        image = Image.fromarray(numpy.array(image_data).reshape(height, width, 4))
        
        brightness_enhancer = ImageEnhance.Brightness(image)
        image = brightness_enhancer.enhance(adjustments["brightness"])

        contrast_enhancer = ImageEnhance.Contrast(image)
        image = contrast_enhancer.enhance(adjustments["contrast"])

        saturation_enhancer = ImageEnhance.Color(image)
        image = saturation_enhancer.enhance(adjustments["saturation"])

        sharpness_enhancer = ImageEnhance.Sharpness(image)
        image = sharpness_enhancer.enhance(adjustments["sharpness"])

        self.images[direction.value]["enhanced"] = ImageQt.ImageQt(image)

    def update_simulated_visualization(self, direction):
        pixmap = self.color_image(self.point_cloud, self.images[direction.value]["enhanced"], self.scale, self.padding_left, self.padding_right, self.adjusted_padding_bottom, direction)
        self.imageLabels[direction.value].setPixmap(pixmap)

    def generate(self):
        point_cloud_layer = self.point_clouds[self.dlg.pointCloudComboBox.currentIndex()]
        vector_layer = self.vector_layers[self.dlg.endPointsComboBox.currentIndex()]
        bathymetry_layer = self.raster_layers[self.dlg.bathymetryComboBox.currentIndex()]

        contour_path = self.dlg.contourLineEdit.text()
        depth_path = self.dlg.depthLineEdit.text()
        west_east_background_path = self.dlg.westEastBackgroundLineEdit.text()
        east_west_background_path = self.dlg.eastWestBackgroundLineEdit.text()

        width = self.dlg.widthSpinBox.value()
        minimum_height = self.dlg.minimumHeightSpinBox.value()
        padding_left = self.dlg.paddingLeftSpinBox.value()
        padding_right = self.dlg.paddingLeftSpinBox.value()
        padding_bottom = self.dlg.paddingBottomSpinBox.value()
        refine_ends = self.dlg.refineEndsCheckBox.isChecked()
        direction = self.direction
        band = self.dlg.bandSpinBox.value()

        end_points, error = self.determine_end_points(point_cloud_layer, vector_layer)

        if len(end_points) == 0:
            QMessageBox.warning(None, "", error)
            return

        point_cloud_path = point_cloud_layer.layer().dataProvider().dataSourceUri()

        self.dlg.showSimulatedVisualizationsButton.hide()
        self.dlg.progressBar.setValue(0)
        self.dlg.progressBar.show()

        if point_cloud_path.endswith(".laz"):
            try:
                l = laspy.open(point_cloud_path, laz_backend=laspy.LazBackend.Laszip)
            except:
                warning("LAZ file support not found. Please install the laszip python package.")
                return
        else:
            l = laspy.open(point_cloud_path)

        points = l.read()
        point_cloud = AirGapPoints(points, *end_points)

        point_cloud.create_contour(contour_path, minimum_height=minimum_height, steps=width, refine_ends=refine_ends, direction=direction, 
            progress_bar = self.dlg.progressBar, bar_steps=33)
        if self.dlg.createDepthFileCheckBox.isChecked():
            point_cloud.create_depth(depth_path, bathymetry_layer.layer(), steps=width, 
                padding_left=padding_left, padding_right=padding_right, direction=direction, band=band)
        scale, adjusted_padding_bottom, ew_image = point_cloud.create_image(east_west_background_path, width=width, padding_left=padding_left, padding_right=padding_right, 
            padding_bottom = padding_bottom, minimum_height=minimum_height, direction=Direction.EAST_TO_WEST, progress_bar = self.dlg.progressBar,
            refine_ends=refine_ends, bar_steps=34)
        scale, adjusted_padding_bottom, we_image = point_cloud.create_image(west_east_background_path, width=width, padding_left=padding_left, padding_right=padding_right, 
            padding_bottom = padding_bottom, minimum_height=minimum_height, direction=Direction.WEST_TO_EAST, progress_bar = self.dlg.progressBar,
            refine_ends=refine_ends, bar_steps=33)

        l.close()

        self.images[Direction.EAST_TO_WEST.value]["original"] = ImageQt.ImageQt(ew_image)
        self.images[Direction.EAST_TO_WEST.value]["enhanced"] = ImageQt.ImageQt(ew_image)

        self.images[Direction.WEST_TO_EAST.value]["original"] = ImageQt.ImageQt(we_image)
        self.images[Direction.WEST_TO_EAST.value]["enhanced"] = ImageQt.ImageQt(we_image)

        self.point_cloud = point_cloud
        self.scale = scale

        self.contour_path = contour_path
        self.depth_path = depth_path
        self.background_path[Direction.EAST_TO_WEST.value] = east_west_background_path
        self.background_path[Direction.WEST_TO_EAST.value] = west_east_background_path

        self.width = width
        self.minimum_height = minimum_height
        self.padding_left = padding_left
        self.padding_right = padding_right
        self.padding_bottom = padding_bottom
        self.adjusted_padding_bottom = adjusted_padding_bottom
        self.refine_ends = refine_ends
        self.direction = direction

        self.dlg.progressBar.hide()
        self.dlg.showSimulatedVisualizationsButton.show()

        self.enhance_image(Direction.EAST_TO_WEST)
        self.update_simulated_visualization(Direction.EAST_TO_WEST)
        self.images[Direction.EAST_TO_WEST.value]["enhanced"].save(self.background_path[Direction.EAST_TO_WEST.value])

        self.enhance_image(Direction.WEST_TO_EAST)
        self.update_simulated_visualization(Direction.WEST_TO_EAST)
        self.images[Direction.WEST_TO_EAST.value]["enhanced"].save(self.background_path[Direction.WEST_TO_EAST.value])

        self.sim_vis.show()
        self.dlg.resize(self.dlg.size().width(), 1)

    def reset_vessel_height(self):
        self.sim_vis.vesselHeightSpinBox.setValue(0)

    def save_adjusted_image(self):
        direction = self.sim_vis.sender().parentWidget().direction
        self.images[direction.value]["enhanced"].save(self.background_path[direction.value])

    def run(self):
        if self.first_start == True:
            self.first_start = False
            self.dlg = AirGapVisDialog()
            self.dlg.contourToolButton.clicked.connect(self.select_contour_file)
            self.dlg.depthToolButton.clicked.connect(self.select_depth_file)
            self.dlg.westEastBackgroundToolButton.clicked.connect(self.select_west_east_background_file)
            self.dlg.eastWestBackgroundToolButton.clicked.connect(self.select_east_west_background_file)
            self.dlg.generateButton.clicked.connect(self.generate)

            self.dlg.createDepthFileCheckBox.stateChanged.connect(self.create_depth_file_changed)
            self.dlg.bathymetryComboBox.currentIndexChanged.connect(self.bathymetry_changed)

            self.sim_vis = SimVisDialog(parent=self.dlg)
            self.sim_vis.westEastGroupBox.direction = Direction.WEST_TO_EAST
            self.sim_vis.eastWestGroupBox.direction = Direction.EAST_TO_WEST

            self.imageLabels[Direction.EAST_TO_WEST.value] = self.sim_vis.eastWestImageLabel
            self.imageLabels[Direction.WEST_TO_EAST.value] = self.sim_vis.westEastImageLabel

            self.sim_vis.vesselHeightSpinBox.valueChanged.connect(self.visualization_option_changed)
            self.sim_vis.clearButton.clicked.connect(self.reset_vessel_height)

            self.sim_vis.bathymetryCheckBox.stateChanged.connect(self.visualization_option_changed)
            self.sim_vis.waterCheckBox.stateChanged.connect(self.visualization_option_changed)
            
            self.sim_vis.westEastBrightnessSlider.valueChanged.connect(self.brightness_changed)
            self.sim_vis.eastWestBrightnessSlider.valueChanged.connect(self.brightness_changed)
            
            self.sim_vis.westEastSaturationSlider.valueChanged.connect(self.saturation_changed)
            self.sim_vis.eastWestSaturationSlider.valueChanged.connect(self.saturation_changed)
            
            self.sim_vis.westEastSharpnessSlider.valueChanged.connect(self.sharpness_changed)
            self.sim_vis.eastWestSharpnessSlider.valueChanged.connect(self.sharpness_changed)

            self.sim_vis.westEastSaveButton.clicked.connect(self.save_adjusted_image)
            self.sim_vis.eastWestSaveButton.clicked.connect(self.save_adjusted_image)

            self.dlg.showSimulatedVisualizationsButton.clicked.connect(self.sim_vis.show)

            self.dlg.showSimulatedVisualizationsButton.hide()
            self.dlg.progressBar.hide()

            if QgsProject.instance().absolutePath():
                os.chdir(QgsProject.instance().absolutePath())
            elif os.getcwd() == "/":
                os.chdir(os.environ["HOME"])

        layers = QgsProject.instance().layerTreeRoot().children()

        self.dlg.resize(self.dlg.size().width(), 1)

        for i in range(self.dlg.pointCloudComboBox.count()):
            self.dlg.pointCloudComboBox.removeItem(0)
        for i in range(self.dlg.endPointsComboBox.count()):
            self.dlg.endPointsComboBox.removeItem(0)
        for i in range(self.dlg.bathymetryComboBox.count()):
            self.dlg.bathymetryComboBox.removeItem(0)

        self.point_clouds = []
        self.vector_layers = []
        self.raster_layers = []

        for l in layers:
            if type(l.layer()) == QgsPointCloudLayer:
                self.dlg.pointCloudComboBox.addItem(l.name())
                self.point_clouds.append(l)
            elif type(l.layer()) == QgsVectorLayer and l.layer().geometryType() == POINT_TYPE:
                self.dlg.endPointsComboBox.addItem(l.name())
                self.vector_layers.append(l)
            elif type(l.layer()) == QgsRasterLayer:
                self.dlg.bathymetryComboBox.addItem(l.name())
                self.raster_layers.append(l)

        self.bathymetry_changed(0)

        self.dlg.show()
