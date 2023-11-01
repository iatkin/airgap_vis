from enum import Enum
from PIL import Image, ImageEnhance
from pyproj import Transformer
from scipy.spatial.transform import Rotation

from qgis.core import *
from qgis.PyQt.QtCore import QCoreApplication

import json
import math
import numpy
import sys

def lm(message):
    QgsMessageLog.logMessage(str(message))

class Direction(Enum):
    EAST_TO_WEST = "east_west"
    WEST_TO_EAST = "west_east"

def find_color(color_grid, closest_y, xyz, r, g, b, black_and_white=False, direction = Direction.WEST_TO_EAST, progress_bar = None, bar_steps = 50):
    length = len(xyz)
    update_interval = int(length/bar_steps)

    if progress_bar:
        progress_bar.setFormat("Creating Background Images: %p%")

    for i in range(length):
        if i != 0 and progress_bar and i % update_interval == 0:
            progress_bar.setValue(progress_bar.value() + 1)
            QCoreApplication.processEvents()

        c = xyz[i]
        x = int(c[0])
        y = int(c[2])


        if black_and_white:
            color_grid[y,x] = False
        else:
            if direction == Direction.WEST_TO_EAST:
                if c[1] < closest_y[y,x]:
                    closest_y[y,x] = c[1]
                    color_grid[y,x] = [
                        r[i],
                        g[i],
                        b[i],
                        255
                    ]
            else:
                if c[1] > closest_y[y,x]:
                    closest_y[y,x] = c[1]
                    color_grid[y,x] = [
                        r[i],
                        g[i],
                        b[i],
                        255
                    ]
    return color_grid

class AirGapPoints():
    def __init__(self, points, western_end, eastern_end):
        self.points = points
        self.xyz = self.points.xyz
        self.mins = points.header.mins
        self.ends = [western_end, eastern_end]
        self.refined_ends = False
        self.maximum_depth = 0

        self.contour = []
        self.depths = []

    def create_contour(self, contour_file, minimum_height=20, steps=1000, refine_ends=True, direction=Direction.WEST_TO_EAST, progress_bar = None, bar_steps=50):
        dx = self.ends[1][0] - self.ends[0][0]
        dy = self.ends[1][1] - self.ends[0][1]
        angle = math.atan(dy/dx)

        self.rotate_points(angle, clockwise=True)

        r_ends = self.rotate_ends(angle, self.ends, clockwise=True)

        if refine_ends:
            refinement_condition = lambda x: x >= minimum_height
            r_ends = self.refine_ends(r_ends, angle, refinement_condition)

        dx = self.ends[1][0] - self.ends[0][0]
        dy = self.ends[1][1] - self.ends[0][1]

        r_step = (r_ends[1][0] - r_ends[0][0])/steps
        contour_x_step = dx/steps
        contour_y_step = dy/steps

        r_contour_points = self.xyz[numpy.logical_and(
            self.xyz[:,0] >= r_ends[0][0],
            self.xyz[:,0] <= r_ends[1][0]
        )]

        r_contour_points -= [r_ends[0][0], 0, 0]
        r_contour_points /= [r_step, 1, 1]
        r_contour_points[:,0] = numpy.floor(r_contour_points[:,0])

        utm_to_wgs = Transformer.from_crs("EPSG:32615", "EPSG:4326", always_xy=True)
        coordinates = []

        update_interval = int(steps/bar_steps)

        if progress_bar:
            progress_bar.setFormat("Creating Contour: %p%")

        for i in range(steps):
            if i != 0 and progress_bar and i % update_interval == 0:
                progress_bar.setValue(progress_bar.value() + 1)
                QCoreApplication.processEvents()

            pixel_group = r_contour_points[r_contour_points[:,0] == i]

            #there should always be a pixel group in a full point cloud, but highly thinned ones
            #might be missing points in a group
            if len(pixel_group) > 0:
                height = numpy.min(pixel_group[:,2])

            if height < minimum_height:
                height = 0

            coordinates.append(utm_to_wgs.transform(
                self.ends[0][0] + i*contour_x_step,
                self.ends[0][1] + i*contour_y_step,
                height
            ))

        if direction == Direction.EAST_TO_WEST:
            coordinates.reverse()

        self.contour = coordinates

        contour_geojson = {
            "type": "FeatureCollection", 
            "features": [{
                "type": "Feature", 
                "properties": { "length": abs(r_ends[1][0] - r_ends[0][0])},
                "geometry": { 
                    "type": "MultiLineString", "coordinates": [coordinates]
                }
            }]
        }
    
        with open(contour_file, "w") as f:
            json.dump(contour_geojson, f)

        self.rotate_points(angle, clockwise=False)

    def create_depth(self, depth_file, layer, steps=1000, padding_left=0, padding_right=0, ends=None, direction=Direction.WEST_TO_EAST, band=1):
        if ends == None:
            ends = self.ends

        if direction == Direction.WEST_TO_EAST:
            start = ends[0]
            end = ends[1]
        else:
            start = ends[1]
            end = ends[0]

        dx = (end[0] - start[0]) / steps
        dy = (end[1] - start[1]) / steps

        start_x = start[0] - (dx * padding_left)
        start_y = start[1] - (dy * padding_left)
        end_x = end[0] + (dx * padding_right)
        end_y = end[1] + (dy * padding_left)
    
        steps = steps + padding_left + padding_right
    
        depths = []
    
        update_interval = int(steps / 100)

        data = layer.dataProvider()
        no_data = data.sourceNoDataValue(band)
        
        for i in range(steps):
            x = start_x + (i*dx)
            y = start_y + (i*dy)

            value, ok = data.sample(QgsPointXY(x,y), band)

            if value == no_data or not ok:
                value = 0

            depths.append(float(value))

        self.depths = depths

        self.maximum_depth = min(depths)
    
        with open(depth_file, "w") as f:
            json.dump(depths, f)

    def create_image(self, image_file, width=1000, padding_left=0, padding_bottom=0, padding_right=0, black_and_white=False, maximum_depth=None, minimum_height=20, direction=Direction.WEST_TO_EAST, refine_ends=True, progress_bar = None, bar_steps = 50):

        if maximum_depth == None:
            maximum_depth = self.maximum_depth

        red = self.points.red
        green = self.points.green
        blue = self.points.blue

        angle = math.atan((self.ends[1][1] - self.ends[0][1])/(self.ends[1][0] - self.ends[0][0]))
        self.rotate_points(angle, clockwise=True)
        r_ends = self.rotate_ends(angle, self.ends, clockwise=True)

        if refine_ends and not self.refined_ends:
            refinement_condition = lambda x: x >= minimum_height
            r_ends = self.refine_ends(r_ends, angle, refinement_condition)

        scale = (r_ends[1][0] - r_ends[0][0])/(width)

        padding_bottom += int(-maximum_depth / scale)

        west_x = r_ends[0][0] - padding_left * scale
        east_x = r_ends[1][0] + padding_right * scale

        image_points = self.points[numpy.where(
            (self.points.x >= west_x) &
            (self.points.x <= east_x)
        )[0]]

        image_xyz = image_points.xyz
        image_r = (image_points.red / 65536) * 256
        image_g = (image_points.green / 65536) * 256
        image_b = (image_points.blue / 65536) * 256

        image_xyz[:,0] -= numpy.min(image_xyz[:,0])
        image_xyz[:,0] /= scale
        image_xyz[:,0] = numpy.floor(image_xyz[:,0])

        image_xyz[:,2] -= numpy.min(image_xyz[:,2])
        image_xyz[:,2] /= scale
        image_xyz[:,2] = numpy.floor(image_xyz[:,2])
        image_xyz[:,2] += padding_bottom

        x_width = int(numpy.max(image_xyz[:,0]) + 1)
        y_width = int(numpy.max(image_xyz[:,2]) + 1)

        if black_and_white:
            color_grid = numpy.ones([y_width, x_width], dtype=bool)
        else:
            color_grid = numpy.full([y_width, x_width, 4], 0, dtype=numpy.uint8)

        if direction == Direction.WEST_TO_EAST:
            closest_y = numpy.full([y_width, x_width], numpy.max(image_xyz[:,1])+1, dtype=numpy.float32)
        else:
            closest_y = numpy.full([y_width, x_width], numpy.min(image_xyz[:,1])-1, dtype=numpy.float32)

        color_grid = find_color(color_grid, closest_y, image_xyz, image_r, image_g, image_b, black_and_white=black_and_white, 
            direction=direction, progress_bar = progress_bar, bar_steps=bar_steps)

        color_height = int(minimum_height / scale)

        self.average_and_color([[padding_bottom, padding_bottom+color_height], [0, padding_left]], color_grid)
        self.average_and_color([[padding_bottom, padding_bottom+color_height], [x_width-padding_right, x_width]], color_grid)

        self.color_obstructions(color_grid, padding_left, padding_bottom, padding_right, color_height)

        if direction == Direction.WEST_TO_EAST:
            color_grid = numpy.fliplr(color_grid)

        image = Image.fromarray(color_grid).rotate(180)

        self.rotate_points(angle, clockwise=False)

        return scale, padding_bottom, image

    def refine_ends(self, r_ends, r_angle, refinement_condition, granularity=0.1):
        refined_west = r_ends[0][0]
        refined_east = r_ends[1][0]

        while not refinement_condition(height := numpy.min(
            self.xyz[numpy.logical_and(self.xyz[:,0] >= refined_west, self.xyz[:,0] < refined_west + granularity)][:,2]
        )):
            refined_west += granularity

        while not refinement_condition(height := numpy.min(
            self.xyz[numpy.logical_and(self.xyz[:,0] >= refined_east, self.xyz[:,0] < refined_east + granularity)][:,2]
        )):
            refined_east -= granularity

        r_ends = [[refined_west, r_ends[0][1]], [refined_east, r_ends[1][1]]]
        self.ends = self.rotate_ends(r_angle, r_ends, clockwise=False)
        self.refined_ends = True

        return r_ends

    def average_and_color(self, extract_ranges, color, draw_lower = True, alpha = 255):
        group_for_color = color[
            extract_ranges[0][0]:extract_ranges[0][1], 
            extract_ranges[1][0]:extract_ranges[1][1]
        ]

        a_red = group_for_color[group_for_color[...,3] == 255][:,0]
        a_green = group_for_color[group_for_color[...,3] == 255][:,1]
        a_blue = group_for_color[group_for_color[...,3] == 255][:,2]

        if len(a_red) > 0:
            a_red = a_red.mean()
        else:
            a_red = 0
        if len(a_green) > 0:
            a_green = a_green.mean()
        else:
            a_green = 0
        if len(a_blue) > 0:
            a_blue = a_blue.mean()
        else:
            a_blue = 0

        if draw_lower:
            color[
                0:extract_ranges[0][0], 
                extract_ranges[1][0]:extract_ranges[1][1]
            ] = [a_red, a_green, a_blue, alpha]

        yl, xl = group_for_color.shape[:2]

        for x in range(xl):
            start = 0
            for y in range(yl):
                if group_for_color[y,x,3] == 0:
                    continue
                else:
                    break

            if y != yl - 1:
                group_for_color[start:y,x] = [a_red, a_green, a_blue, alpha]

        color[
            extract_ranges[0][0]:extract_ranges[0][1], 
            extract_ranges[1][0]:extract_ranges[1][1]
        ] = group_for_color

    def color_obstructions(self, colors, padding_left, padding_bottom, padding_right, color_height):
        yl, xl = colors.shape[:2]

        start_i = None

        for i in range(padding_right, xl - padding_left):
            mean = numpy.mean(colors[padding_bottom:padding_bottom+color_height,i])
            if mean > 0 and start_i == None:
                start_i = i
            elif mean == 0 and start_i != None:
                self.average_and_color([[padding_bottom, padding_bottom+color_height],[start_i, i]], colors)
                start_i = None

        if start_i:
            self.average_and_color([[padding_bottom, padding_bottom+color_height],[start_i, i]], colors)

    def rotate_ends(self, angle, ends, clockwise=False):
        if clockwise:
            angle = -angle

        rotation = Rotation.from_euler("z", angle)

        points = numpy.asarray([[ends[0][0], ends[0][1], 0], [ends[1][0], ends[1][1], 0]])
        points -= self.mins
        points = rotation.apply(points)
        points += self.mins

        return [[points[0][0], points[0][1]], [points[1][0], points[1][1]]]

    def rotate_points(self, angle, clockwise=False):
        if clockwise:
            angle = -angle

        rotation = Rotation.from_euler("z", angle)
        
        self.xyz -= self.mins
        self.xyz = rotation.apply(self.xyz)
        self.xyz += self.mins

        self.points.xyz = self.xyz
