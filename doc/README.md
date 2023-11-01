# airgap_vis
A Javascript module and accompanying QGIS plugin for displaying an air gap visualization generated from a point cloud.

## Javscript Module

The module provides two classes. AirGapVisualization uses air gap data from tidesandcurrents.noaa.gov and requires a station ID that provides air gap data. WaterGageVisualization uses gage data from water.weather.gov and requires one or two gage IDs. If two gages are provided, the air gap is calculated using an interpolated value based on distance from the area being visualized.

In places where "east to west" and "west to east" images are referenced, this is based on moving from the left edge of the image to the right edge regardless of the angle of the bridge or other location. 

<a href="https://iatkin.github.io/airgap_vis/">Interactive Demo</a>

<img src="https://raw.githubusercontent.com/iatkin/airgap_vis/main/doc/img/visualization.png">

1. Air Gap Area - Mousing over this area will show the current air gap at that point. When a vessel height is entered, the background turns green for areas with enough clearance and red for obstructions and areas without enough clearance. When initializing the visualization, default marker locations may be added. These are defined as pixels from the left edge of the initial image that will be used.

2. Vessel Height - The height in meters to use when determining clearance. The visualization is updated as the number is input.

3. Orientation Display - Swaps between the upstream and downstream views of the location. Upstream and downstream is determined using a combination of the `initialOrientation` and `upstreamDirection` options.

4. Data Update - The timestamp of the currently used data along. Whether data is considered recent (green) or out of date (red) is controlled with the `staleData` option.

### Requirements
There are no external Javascript dependencies.

The visualization itself requires three files, a contour file and two background images, and may use an optional bathymetry file. These are most easily created with the QGIS plugin.

### Usage

`<div id="elementID"></div>`
`<script type="module">`
`    import {AirGapVisualization} from "./airgap.js"`
` `
`    var options = { ... }`
`    var visualizationID = "elementID"`
`    var visualization = new AirGapVisualization(visualizationID, options)`
`</script>`

### Options
Most options are required and are shared between AirGapVisualization and WaterGageVisualization.

Paths may be relative or absolute.

#### Shared

|Option|Values|Default|Required|Description|
|------|------|-------|--------|-----------|
|bathymetry|String path||*Optional*|The path of the bathymetry JSON file|
|contour|String path||**Required**|The path of the contour GeoJSON file|
|disableControls|boolean|false|*Optional*|Set to true to disable vessel height and direction switching controls. Even if disabled, they can still be controlled programatically.|
|images|dictionary||**Required**|A dictionary containing two keys, "east_west" and "west_east". To use a single image, set both keys to the same value.|
|images.east_west|String path||**Required**|The path of the east to west image|
|images.west_east|String path||**Required**|The path of the west to east image|
|initialOrientation|"up" or "down"||**Required**|Whether to initially show the upstream or downstream view|
|markers|Array of integers||*Optional*|An array of x positions relative to the left edge of the initial image that will be shown|
|padding|dictionary||**Required**|A dictionary containing three keys, "bottom", "left" and "right"|
|padding.bottom|integer||**Required**|The number of additional bottom pixels in the point cloud images|
|padding.left|integer||**Required**|The number of additional left side pixels in the point cloud images|
|padding.right|integer||**Required**|The number of additional right side pixels in the point cloud images|
|upstreamDirection|"east_west" or "west_east"||**Required**|Which direction corresponds with upstream. Used in conjuction with `initialOrientation` for image selection and labeling.|

#### AirGapVisualization

|Option|Values|Default|Required|Description|
|------|------|-------|--------|-----------|
|baseHeight|float||**Required**|The height *in the point cloud* for the point that the air gap data is relative to. For example, for the Crescent City Air Gap, this point is the western edge of the navigation channel.|
|refreshInterval|integer milliseconds|6 * 60 * 1000|The amount of time to wait before reloading air gap data|
|staleData|integer milliseconds|30 * 60 * 1000|The amount of time that must pass before air gap data is considered out of date. Data may become out of date if the visualization is not in the foreground.|
|stationID|integer||**Required**|The station ID to use. Must be a station with air gap data.|

#### WaterGageVisualization

|Option|Values|Default|Required|Description|
|------|------|-------|--------|-----------|
|baseHeight|float||**Required**|For point cloud locations with Coast Pilot or similar data, this is the base vertical clearance. No recommendation is given for other locations.|
|gageDistances|array of two floats||**Required for two gages**|The river distance in meters of the gages from the point cloud location|
|gageIDs|array of one or two strings||**Required**|The gage IDs to use|
|refreshInterval|integer milliseconds|15 * 60 * 1000|*Optional*|The amount of time to wait before reloading gage data|
|staleData|integer milliseconds|120 * 60 * 1000|*Optional*|The amount of time that must pass before air gap data is considered out of date. Data may become out of date if the visualization is not in the foreground.|
|waterLevelAdjustment|float|*Optional*||Any additional water level adjustment that may be needed. Positive values decrease the air gap.|

## QGIS Plugin

### Requirements
#### QGIS Version
Tested on QGIS 3.28 LTR and 3.32

#### Python Modules
- laspy
- laszip (optional)
    - This is only required if using compressed LAZ files.
- numpy
- pillow prior to version 10
    - Version 10 removed support for Qt 5 which is used by QGIS.
- pyproj
- scipy

### Use

<img src="https://raw.githubusercontent.com/iatkin/airgap_vis/main/doc/img/generation.png">

1. Select the point cloud, end point layer and bathymetry layer. The applicable layers for each type will be ordered as they appear in the Layers panel.
2. Modify the Generation Options as needed.
3. Set the Output Paths.
4. Click Generate to create the files.

Once the files have been generated, a simplified version of the air gap visualization will be displayed in order to check the generated files. The initial window will still be open, and a Show Simulated Visualizations button is added above the Generate button.

<img src="https://raw.githubusercontent.com/iatkin/airgap_vis/main/doc/img/simulated_visualization.png">

Both the West to East and East to West views are shown. Vessel Height may be entered at the top of the window to inspect the contour and check if any stray extra points may have caused issues with the contour generation. The water level is set to the 0m elevation of the point cloud and may be disabled along with the bathymetry display to inspect the background image.

Three image parameters may be adjusted using the dials underneath each image. Since the image itself is fully transparent in areas that do not have points, these parameters do not affect the background. The save button underneath the dials overwrites the original image.

### Options
#### Layers
|Layer|Description|
|-------|-----------|
|Point Cloud|Point clouds are reloaded from their original source file. For performance reasons, it is recommended to use uncompressed .las files.|
|End Points|This layer may be any point-based layer. The overall layer can contain any number of points, but exactly two must be within the bounds of the point cloud. For example, if multiple point clouds have been added to the project for generation, a single point layer may be used to hold all the end points.|
|Bathymetry|All raster layers will be listed however usable layers must be a local file and not an online resource like a WCS layer. If the layer has multiple bands, a band selector will appear|

#### Generation Options
|Option|Description|
|------|-----------|
|Width|The number bins/pixels to use when generating the contour.|
|Minimum Height|The minimum height value in meters to be considered part of the air gap. This option exists both to properly block off bridge pillars which may have spotty coverage at the base and to enable the Refine Ends.|
|Refine Ends|This sets whether to automatically adjust the contour end points along the line formed between them until the end points meet the minimum height value. This allows flexibility in setting the points as it can be hard to go exactly shore to shore or pillar to pillar.|
|Side Padding|The number of extra pixels to add to each side of the generated images for extra visual context e.g. shoreside buildings.|
|Bottom Padding|The number of extra pixels to add to the bottom of the generated images.|

#### Output Paths
The three dot (…) buttons are used to bring up the file chooser. The default directory is the location of the project file if the project has been saved. If it has not, then it is the Documents directory on Windows or the user's home area on Linux and macOS.

### Installation Prerequisites

Any installation paths are for the default QGIS profile. Modify as needed for other profiles.

#### Windows via OSGeo4W
1. Install numpy, pillow, pyproj and scipy using the OSGeo4W installer. Make sure the version of pillow is not 10.
2. Using the OSgeo4W shell, install laspy and laszip with `pip install laspy laszip`

#### macOS
The Mac version comes preinstalled with numpy, pillow and pyproj.

1. In Terminal, go to the location of QGIS such as /Applications or ~/Applications e.g. `cd ~/Applications`.
2. Go inside QGIS's app bundle to its internal executables with `cd QGIS.app/Contents/MacOS/bin`.
3. Install laspy, laszip and scipy, `./pip install laspy laszip scipy --target=$HOME/Library/Application\ Support/QGIS/QGIS3/profiles/default/python`.

#### Linux (Flatpak)
It is recommended to use QGIS installed from a Flatpak.

1. Install QGIS with `flatpak install --from https://dl.flathub.org/repo/appstream/org.qgis.qgis.flatpakref`
2. The installation comes with numpy and pyproj. Install the other four required modules with  
   `flatpak run --devel --command=pip3 org.qgis.qgis install laspy laszip pillow==9.5.0 scipy --target=$HOME/.var/app/org.qgis.qgis/data/QGIS/QGIS3/profiles/default/python`
3. The above may fail due to the KDE SDK runtime being unavailable. flatpak will give the missing package which will be along the lines of  
   `runtime/org.kde.Sdk/x86_64/5.15-21.08`. Install this package with  
   `flatpak install runtime/org.kde.Sdk/x86_64/5.15-21.08`  
   or the equivalent then run step 2 again.

#### Linux (distribution repository or QGIS repository)
Notes on installing

- **Fedora 38**  
  Use a Flatpak. QGIS crashes from an unrelated bug when enabling the plugin.

- **Rocky Linux 8 and presumably RHEL 8**  
  The version in the repository is a Flatpak. Follow the Flatpak instructions starting from step 2.

- **openSUSE Leap 15.5**  
  Use a Flatpak. The version in the official repository does not support point clouds.

- **openSUSE Tumbleweed**
  1. If QGIS has been installed from the repository, numpy and pyproj were installed as dependencies. Use the package manager to install `python3-scipy`.
  2. In a terminal window, install the remaining modules with
     `python3 -m pip install laspy laszip pillow==9.5.0 --target=$HOME/.local/share/QGIS/QGIS3/profiles/default/python`

- **Ubuntu 23.10**
  Use a Flatpak. The version in both the official repository and the QGIS repository does not support point clouds.

- Other distributions have not been tested.

#### FreeBSD 13.2
Note: LAZ files are not currently supported on FreeBSD.

If QGIS was installed from the repository, pyproj will already be installed. The version of pillow that is included as a QGIS dependency is version 10. The version of scipy has a bug that causes QGIS to crash when enabling the plugin. Laspy also needs to be installed.

1. Install cmake and lfortran e.g. `pkg install cmake lfortran`.
2. Create a symbolic link from /usr/local/bin/gfortran12 to /usr/local/bin/gfortran, `ln -s /usr/local/bin/gfortran12 /usr/local/bin/gfortran`.
3. Create a symbolic link from /usr/local/bin/python3.9 to /usr/local/bin/python3, `ln -s /usr/local/bin/python3.9 /usr/local/bin/python3`.
4. Install the required packages with `pip install laspy pillow==9.5.0 scipy --target=$HOME/.local/share/QGIS/QGIS3/profiles/default/python`. This will also install numpy into profile directory due to it being a dependency of laspy and scipy.

#### OpenBSD
Not currently tested

### Installation
1. In QGIS's menu bar, go to Settings > User Profiles > Open Active Profile Folder.
2. In the resulting window, go to `python` then `plugins`. Create the `plugins` directory if it has not been created.
3. Copy the `airgap_vis` directory to `plugins`.
4. In QGIS's menu bar, go to Plugins > Manage and Install Plugins. In the Installed tab, check AirGapVis.
