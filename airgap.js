Object.defineProperty(Array.prototype, "last", {
    get() { return this[this.length - 1] }
})

Math.sum = function() {
    return Array.from(arguments).reduce((a,b) => a + b)
}

const Direction = Object.freeze({
    EAST_TO_WEST: "east_west",
    WEST_TO_EAST: "west_east"
})

class AirGapVisualization {
    constructor(elementID, options) {
        this.options = options
        this.options.elementID = elementID

        this._orientation = 0
        this._vesselHeight = null

        this.depths = []
        this.geoJSON = null
        this.heights = []
        this.groupedHeights = []
        this.metersPerPixel = {"x": null, "y": null}
        this.showImpassable = false
        this.waterPixels = null

        this.elements = {}
        this.elements.outer = document.getElementById(elementID)

        this.elements.main = document.createElement("div")
        this.elements.main.style.position = "relative"
        this.elements.main.style.fontFamily = "system-ui, sans-serif"
        this.elements.outer.append(this.elements.main)

        this.elements.bridge = document.createElement("img")
        this.elements.main.append(this.elements.bridge)

        this.elements.ui = document.createElement("div")
        this.elements.ui.style.position = "relative"
        this.elements.main.append(this.elements.ui)

        this.elements.controls = document.createElement("div")
        this.elements.controls.style.margin = "10px 0px"
        this.elements.ui.append(this.elements.controls)

        this.elements.markers = []

        for (var i = 0; i < this.options.markers.length; ++i) {
            var marker = document.createElement("div")
            marker.style.backgroundColor = "#F8F8F8"
            marker.style.border = "1px solid black"
            marker.style.borderRadius = "5px 0px 0px 5px"
            marker.style.display = "none"
            marker.style.padding = "5px"
            marker.style.position = "absolute"
            marker.style.width = "65px"

            this.elements.markers.push(marker)
        }
        this.elements.airgap = this.elements.markers[0]

        this.elements.vesselHeight = {
            "label": document.createElement("label"),
            "input": document.createElement("input")
        }
        this.elements.vesselHeight.label.textContent = "Vessel Height: "
        this.elements.controls.append(this.elements.vesselHeight.label)

        this.elements.vesselHeight.input.type = "text"
        this.elements.vesselHeight.input.style.width = "4em"
        this.elements.vesselHeight.label.append(this.elements.vesselHeight.input)
        this.elements.vesselHeight.label.append(" m ")

        this.elements.clearHeight = document.createElement("input")
        this.elements.controls.append(this.elements.clearHeight)

        this.elements.clearHeight.type = "button"
        this.elements.clearHeight.value = "Clear"

        this.elements.clearHeight.addEventListener("click", (e) => {
            this.elements.vesselHeight.input.value = ""
            this.vesselHeight = null

            var element = this.elements.impassable
            element.getContext("2d").clearRect(0,0,element.width,element.height)
        })

        this.elements.vesselHeight.input.addEventListener("change", (e) => {
            this.vesselHeight = Number(e.target.value)
        })
        this.elements.vesselHeight.input.addEventListener("keyup", (e) => {
            this.vesselHeight = Number(e.target.value)
        })

        this._createOrientationSwitch()

        this.elements.info = document.createElement("div")
        this.elements.info.style.borderBottom = "1px solid #888888"
        this.elements.info.style.paddingBottom = "5px"
        this.elements.ui.append(this.elements.info)

        if (this.options.disableControls) {
            this.elements.controls.style.display = "none"
        }

        this.elements.position = document.createElement("span")
        this.elements.position.style.display = "inline-block"
        this.elements.position.style.width = "50%"
        this.elements.info.append(this.elements.position)

        this.elements.refreshDate = document.createElement("span")
        this.elements.refreshDate.style.padding = "0px 5px"
        this.elements.refreshDate.style.position = "absolute"
        this.elements.refreshDate.style.right = "20px"
        this.elements.info.append(this.elements.refreshDate)

        this.elements.refreshSymbol = document.createElement("span")
        this.elements.refreshSymbol.style.display = "inline-block"
        this.elements.refreshSymbol.style.position = "absolute"
        this.elements.refreshSymbol.style.right = "0px"
        this.elements.refreshSymbol.style.width = "20px"
        this.elements.refreshSymbol.style.height = "20px"
        this.elements.refreshSymbol.style.lineHeight = "20px"
        this.elements.refreshSymbol.style.fontSize = "15px"
        this.elements.refreshSymbol.style.textAlign = "center"
        this.elements.refreshSymbol.style.borderRadius = "5px"
        this.elements.refreshSymbol.style.color = "white"
        this.elements.refreshSymbol.fontWeight = "bold"
        this.elements.info.append(this.elements.refreshSymbol)

        var airgapPromise = this.loadAirGap()
        var depthPromise = this._loadDepths()
        var heightPromise = this._loadHeights()
        var imagePromise = new Promise((resolve, reject) => {
            this._loadBridgeImage()

            this.elements.bridge.onload = () => {
                resolve()
                this.elements.ui.style.width = `${this.elements.bridge.clientWidth}px`
            }
        })

        Promise.all([airgapPromise, depthPromise, heightPromise, imagePromise]).then(() => {
            this.metersPerPixel = {
                "x": this.geoJSON.features[0].properties.length / this.waterwayWidth,
                "y": this.geoJSON.features[0].properties.length / this.waterwayWidth
            }

            this.depthHeight = Math.floor(Math.abs(Math.min(...this.depths) / this.metersPerPixel.y)) + this.options.padding.bottom

            this._createCanvas()
            this._groupHeights()
            this._drawWater()
            this._addHandlers()
        })

        this.refreshInterval = window.setInterval(() => {
            this.loadAirGap().then(() => {
                this._drawWater()
                this.vesselHeight = this.vesselHeight
            })
        }, this.options.refreshInterval)
    }

    _addHandlers() {
        this.elements.water.addEventListener("mousemove", (e) => {
            for (var i = 1; i < this.options.markers.length; ++i) {
                this.elements.markers[i].style.display = "none"
            }

            this._displayAirGap(this.elements.markers[0], e.offsetX)
            this._displayPosition(e)
        })

        this.elements.water.addEventListener("mouseout", (e) => {
            this._resetAirGap()
            this.elements.position.textContent = ""
        })
    }

    _createCanvas() {
        this.elements.impassable = document.createElement("canvas")
        this.elements.impassable.height = this.elements.bridge.height
        this.elements.impassable.width = this.elements.bridge.width

        this.elements.impassable.style.position = "absolute"
        this.elements.impassable.style.left = "0px"
        this.elements.impassable.style.top = "0px"

        this.elements.height = document.createElement("canvas")
        this.elements.height.height = this.elements.bridge.height
        this.elements.height.width = this.elements.bridge.width

        this.elements.height.style.position = "absolute"
        this.elements.height.style.left = "0px"
        this.elements.height.style.top = "0px"

        this.elements.water = document.createElement("canvas")
        this.elements.water.height = this.elements.bridge.height
        this.elements.water.width = this.elements.bridge.width

        this.elements.water.style.position = "absolute"
        this.elements.water.style.left = "0px"
        this.elements.water.style.top = "0px"

        this.elements.main.append(this.elements.impassable)
        this.elements.main.append(this.elements.height)

        for (var marker of this.elements.markers) {
            this.elements.main.append(marker)
        }

        this.elements.main.append(this.elements.water)
    }

    _createOrientationSwitch() {
        this.elements.orientation = document.createElement("span")
        this.elements.orientation.style.marginLeft = "10px"
        this.elements.controls.append(this.elements.orientation)

        this.elements.orientationLabel = document.createElement("label")

        if (this.options.initialOrientation == "up") {
            this.elements.orientationLabel.textContent = "Viewing Upstream "
        }
        else {
            this.elements.orientationLabel.textContent = "Viewing Downstream "
        }

        this.elements.orientationChange = document.createElement("input")
        this.elements.orientationChange.type = "button"
        this.elements.orientationChange.value = "Change"    
        this.elements.orientationChange.addEventListener("click", () => {
            this._setOrientation()
        })

        this.elements.orientation.append(this.elements.orientationLabel)
        this.elements.orientation.append(this.elements.orientationChange)
    }

    _displayAirGap(marker, offsetX, clear = true) {
        var x = offsetX - this.options.padding.left
        
        var context = this.elements.height.getContext("2d")

        if (clear) {
            context.clearRect(0,0,this.elements.height.width,this.elements.height.height)
        }

        if (x < 0 || x > this.waterwayWidth) {
            this._resetAirGap()
        }
        else {
            var value = this._valueForPosition(x)

            if (value > 0) {
                var h = Math.floor((value / this.metersPerPixel.y))
                var y = this.elements.height.height - this.waterPixels - h

                context.fillStyle = "black"
                context.fillRect(offsetX, y, 1, h)

                var element = marker
                element.style.display = "block"
                element.innerHTML = `${value.toFixed(2)}m<br>${(value*3.281).toFixed(2)}ft`
                element.style.top = `${y+h/2-23}px`

                var width = element.offsetWidth

                if (this.orientation == 180) {
                    element.style.left = `${this.elements.height.width - offsetX - width}px`
                }
                else {
                    element.style.left = `${offsetX - width + 1}px`
                }
            }
            else {
                marker.innerHTML = "Blocked<br>by pillar"
            }
        }
    }

    _displayPosition(moveEvent) {
        var coordinates = this.coordinates
        var startPoint = coordinates[0]
        var endPoint = coordinates.last
        var pixelLength = this.waterwayWidth
        var xWidth = (endPoint[0] - startPoint[0])/pixelLength
        var yWidth = (endPoint[1] - startPoint[1])/pixelLength

        var x = Math.abs(startPoint[0] + xWidth*moveEvent.offsetX)
        var y = Math.abs(startPoint[1] + yWidth*moveEvent.offsetX)

        var xDegrees = parseInt(x)
        var xMinutes = (x % 1) * 60
        var xSeconds = (xMinutes % 1) * 60

        var yDegrees = parseInt(y)
        var yMinutes = (y % 1) * 60
        var ySeconds = (yMinutes % 1) * 60

        var xString = `${xDegrees}\u00B0 ${xMinutes<10? "0": ""}${parseInt(xMinutes)}' ${xSeconds<10? "0": ""}${xSeconds.toFixed(4)}"`
        var yString = `${yDegrees}\u00B0 ${yMinutes<10? "0": ""}${parseInt(yMinutes)}' ${ySeconds<10? "0": ""}${ySeconds.toFixed(4)}"`

        this.elements.position.textContent = `${yString} N, ${xString} W`
    }

    _groupHeights() {
        var coordinates = this.coordinates

        var startPoint = coordinates[0]
        var endPoint = coordinates.last
        var pixelLength = this.waterwayWidth
        var xWidth = (endPoint[0] - startPoint[0])/pixelLength
        var yWidth = (endPoint[1] - startPoint[1])/pixelLength

        for (var i = 0; i < pixelLength; ++i) {
            this.groupedHeights.push([])
        }

        for (var i = 0; i < coordinates.length - 1; ++i) {
            var c = coordinates[i]

            var x = c[0] - startPoint[0]
            var y = c[1] - startPoint[1]

            var index = parseInt(x/xWidth)

            this.groupedHeights[index].push(c[2])
        }
        this.groupedHeights.last.push(coordinates.last[2])
    }

    _drawDepths() {
        var context = this.elements.water.getContext("2d")
        context.fillStyle = "rgba(63,63,63,1)"
        var x = 0
        var y = this.elements.water.height - this.depthHeight

        for (var i = 0; i < this.depths.length; ++i) {
            context.fillRect(x+i,y + Math.abs(this.depths[i] / this.metersPerPixel.y),1,this.depthHeight)
        }
    }

    _drawWater() {
        var airgap = this.airgap

        var width = this.elements.water.width
        var height = this.depthHeight + (this.gapChange / this.metersPerPixel.y)
        var x = 0
        var y = this.elements.water.height - height

        this.waterPixels = height

        var context = this.elements.water.getContext("2d")
        context.clearRect(0,0,this.elements.water.width, this.elements.water.height)
        context.fillStyle = "rgba(0,133,202,0.75)"
        context.fillRect(x,y,width,height)

        if (this.showImpassable) {
            this._showImpassable()
        }

        if (this.depths.length > 0) {
            this._drawDepths()
        }

        this._resetAirGap()
    }

    _error(message) {
        this.elements.refreshDate.textContent = message
        this.elements.refreshSymbol.textContent = "!"
        this.elements.refreshSymbol.style.backgroundColor = "red"
        this.elements.refreshDate.style.color = "red"
    }

    _loadBridgeImage() {
        var orientation = null
        var upstream = this.options.upstreamDirection

        if (this.orientation == 0) {
            orientation = this.options.initialOrientation
        }
        else {
            orientation = this.options.initialOrientation == "up" ? "down" : "up"
        }

        if ((orientation == "up" && upstream == "east_west") || (orientation == "down" && upstream == "west_east")) {
            this.elements.bridge.src = this.options.images.east_west
        }
        else {
            this.elements.bridge.src = this.options.images.west_east
        } 
    }

    async _loadDepths() {
        if (this.options.bathymetry) {
            var response = await fetch(this.options.bathymetry)
            
            var initial = this.options.initialOrientation
            var upstream = this.options.upstreamDirection

            if (!response.ok) {
                alert("Unable to load depths")
                return
            }

            this.depths = await response.json()

            if ((initial == "up" && upstream == "east_west") || (initial == "down" && upstream == "west_east")) {
                this.depths.reverse()
            }
        }
    }

    async _loadHeights() {
        var response = await fetch(this.options.contour)
        var initial = this.options.initialOrientation
        var upstream = this.options.upstreamDirection

        if (!response.ok) {
            alert("Unable to load heights")
            return
        }

        this.geoJSON = await response.json()

        if ((initial == "up" && upstream == "east_west") || (initial == "down" && upstream == "west_east")) {
            this.coordinates.reverse()
        }

        for (var c of this.coordinates) {
            this.heights.push(c[2])
        }
    }

    _resetAirGap() {
        this._displayAirGap(this.elements.markers[0], this.options.markers[0], true)
        for (var i = 1; i < this.options.markers.length; ++i) { 
            this._displayAirGap(this.elements.markers[i], this.options.markers[i], false)
        }
    }

    _setOrientation() {
        this.orientation = (this._orientation + 180) % 360
        this._resetAirGap()
    }

    _showImpassable() {
        var context = this.elements.impassable.getContext("2d")
        var previousValue = null
        var width = this.waterwayWidth

        context.clearRect(0,0,this.elements.impassable.width, this.elements.impassable.height)

        for (var i = 0; i < width; ++i) {
            var value = this._valueForPosition(i)

            if (value == 0) {
                var h = (previousValue / this.metersPerPixel.y)
                var x = i + this.options.padding.left
                var y = this.elements.impassable.height - this.waterPixels - h

                context.fillStyle = "rgba(255,0,0,0.75)"
                context.fillRect(x,y,1,h)
            }
            else {
                previousValue = value
            }
            if (value < this.vesselHeight) {
                var h = (value / this.metersPerPixel.y)
                var x = i + this.options.padding.left
                var y = this.elements.impassable.height - this.waterPixels - h

                context.fillStyle = "rgba(255,0,0,0.75)"
                context.fillRect(x,y,1,h)
            }
            else {
                var h = (value / this.metersPerPixel.y)
                var x = i + this.options.padding.left
                var y = this.elements.impassable.height - this.waterPixels - h

                context.fillStyle = "rgba(0,255,0,0.75)"
                context.fillRect(x,y,1,h)
            }
        }
    }

    _valueForPosition(position) {
        position = Math.min(position, this.groupedHeights.length-1)

        while (position > -1 && this.groupedHeights[position].length == 0) {
            position -= 1
        }

        var value = Math.min(...this.groupedHeights[position])

        return value == 0 ? 0 : value - this.gapChange
    }

    async loadAirGap() {
        var response = await fetch(this.airGapURL)

        if (!response.ok) {
            alert("Unable to get air gap")
            return 0
        }

        var json = await response.json()

        this.refreshDate = new Date(`${json["data"][0]["t"]}Z`)

        var airgap = Number(json["data"][0]["v"])

        if (this.airgap && airgap == 0) {
            alert("Unable to load air gap. Keeping previous value.")
        }
        else if (airgap == 0) {
            alert("Unable to load air gap. Retrying in 6 minutes")
            this.airgap = 0
        }
        else {
            this.airgap = airgap
        }

        return this.airgap
    }

    get airGapURL() {
        return `https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?date=latest&station=${this.options.stationID}&product=air_gap&time_zone=gmt&units=metric&format=json`
    }

    get coordinates() {
        return this.geoJSON.features[0].geometry.coordinates[0]
    }

    get gapChange() {
        return this.options.baseHeight - this.airgap
    }

    get orientation() {
        return this._orientation
    }

    set orientation(value) {
        this._orientation = value

        if (value == 0) {
            if (this.options.initialOrientation == "up") {
                this.elements.orientationLabel.textContent = "Viewing Upstream "
            }
            else {
                this.elements.orientationLabel.textContent = "Viewing Downstream "
            }
        }
        else {
            if (this.options.initialOrientation == "up") {
                this.elements.orientationLabel.textContent = "Viewing Downstream "
            }
            else {
                this.elements.orientationLabel.textContent = "Viewing Upstream "
            }
        }
        
        this._loadBridgeImage()
        this.elements.water.style.transform = `rotateY(${value}deg)`
        this.elements.height.style.transform = `rotateY(${value}deg)`
        this.elements.impassable.style.transform = `rotateY(${value}deg)`
    }

    get refreshDate() {
        return this._refreshDate
    }

    set refreshDate(date) {
        this._refreshDate = date
        var elapsedTime = Date.now() - date

        this.elements.refreshDate.textContent = `${date.toLocaleString()} (${Math.floor(elapsedTime/60000)} minutes ago)`

        if (elapsedTime < this.options.staleData) {
            this.elements.refreshSymbol.textContent = "\u2713"
            this.elements.refreshSymbol.style.backgroundColor = "green"
            this.elements.refreshDate.style.color = "green"
        }
        else {
            this.elements.refreshSymbol.textContent = "!"
            this.elements.refreshSymbol.style.backgroundColor = "red"
            this.elements.refreshDate.style.color = "red"
        }

        if (!this.refreshDateInterval) {
            this.refreshDateInterval = window.setInterval(() => {
                this.refreshDate = this.refreshDate
            }, 60000)
        }
    }

    get vesselHeight() {
        return this._vesselHeight
    }

    set vesselHeight(height) {
        this._vesselHeight = Number(height)

        if (isNaN(this._vesselHeight)) {
            this.elements.vesselHeight.input.style.backgroundColor = "rgb(255, 127, 127)"
            var element = this.elements.impassable
            element.getContext("2d").clearRect(0,0,element.width,element.height)
        }
        else if (this._vesselHeight == 0) {
            this.elements.clearHeight.click()
        }
        else {
            this.elements.vesselHeight.input.style.backgroundColor = "white"
            this._showImpassable()
        }
    }

    get waterwayWidth() {
        return this.elements.bridge.width - this.options.padding.left - this.options.padding.right
    }
}

class WaterGageVisualization extends AirGapVisualization {
    async loadAirGap() {
        var xmlParsers = {}

        for (var gage of this.options.gageIDs) {
            var response = await fetch(this.urlForGage(gage))
            var data = await response.text()
            var xml = new DOMParser().parseFromString(data, "text/xml")

            xmlParsers[gage] = xml
        }

        var levels = []
        var dates = []
        var downGages = []

        for (var gage of this.options.gageIDs) {
            if (xmlParsers[gage].querySelector("primary")) {
                levels.push(Number(xmlParsers[gage].querySelector("primary").textContent) * 0.3048)
                dates.push(new Date(xmlParsers[gage].querySelector("valid").textContent))

            }
            else {
                downGages.push(gage)
            }
        }

        if (downGages.length > 0) {
            var message = null

            if (downGages.length == 1) {
                message = `Unable to load gage ${downGages[0]}`
            }
            else if (downGages.length == 2) {
                message = `Unable to load gages ${downGages[0]} and ${downGages[1]}`
            }
            else {
                message = `Unable to load gages `

                for (var i = 0; i < downGages.length - 1; ++i) {
                    message += `${downGages[i]}, `
                }

                message += `and ${downGages.last}`
            }

            this._error(message)
        }
        else if (this.options.gageIDs.length == 1) {
            this.refreshDate = dates[0]
            this.airgap = this.options.baseHeight - this.options.waterLevelAdjustment - levels[0]
        }
        else if (this.options.gageIDs.length == 0) {
            this.elements.refreshDate.textContent = "No Gage"
            this.airgap = this.options.baseHeight - this.options.waterLevelAdjustment
        }
        else {
            this.refreshDate = dates[0]
            var changePerMeter = (levels[1] - levels[0])/(Math.sum(...this.options.gageDistances))
            this.airgap = this.options.baseHeight - this.options.waterLevelAdjustment - levels[0] + (changePerMeter * this.options.gageDistances[0])
        }
        
        return this.airgap
    }
    
    urlForGage(gage) {
        return `https://water.weather.gov/ahps2/hydrograph_to_xml.php?gage=${gage}&output=xml`
    }
}

export {AirGapVisualization, Direction, WaterGageVisualization}
