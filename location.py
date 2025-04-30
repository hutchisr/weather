import time
import objc
from typing import Dict, Any, Optional, Union
from Foundation import NSObject, NSRunLoop, NSDate
from CoreLocation import (
    CLLocationManager,
    kCLDistanceFilterNone,
    kCLLocationAccuracyBest,
    kCLLocationAccuracyBestForNavigation,
    kCLLocationAccuracyNearestTenMeters,
    kCLLocationAccuracyHundredMeters,
    kCLLocationAccuracyKilometer,
    kCLLocationAccuracyThreeKilometers,
    # Authorization status constants
    kCLAuthorizationStatusNotDetermined,
    kCLAuthorizationStatusRestricted,
    kCLAuthorizationStatusDenied,
    kCLAuthorizationStatusAuthorizedAlways,
    kCLAuthorizationStatusAuthorizedWhenInUse,
    # Error code constants
    kCLErrorLocationUnknown,
    kCLErrorDenied
)
from fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("location")

# Cache for location data to avoid frequent requests
_location_cache = {
    "data": None,
    "timestamp": 0,
    "cache_duration": 30  # Cache valid for 30 seconds by default
}

class LocationDelegate(NSObject):
    """Delegate class to receive location updates from CoreLocation"""

    def init(self):
        self = objc.super(LocationDelegate, self).init()
        if self is None:
            return None
        self.location = None
        self.location_error = None
        self.is_updated = False
        return self

    def locationManager_didUpdateLocations_(self, manager, locations):
        """Called when location updates are received"""
        self.location = locations[-1]  # Get the most recent location
        self.is_updated = True

    def locationManager_didFailWithError_(self, manager, error):
        """Called when location services fail"""
        self.location_error = error
        self.is_updated = True

def _format_location_data(location) -> Optional[Dict[str, Any]]:
    """
    Format location data from CLLocation object to dictionary

    Args:
        location: CoreLocation object or None

    Returns:
        Dictionary with formatted location data or None if location is None
    """
    if not location:
        return None

    try:
        return {
            "latitude": location.coordinate().latitude,
            "longitude": location.coordinate().longitude,
            "accuracy": location.horizontalAccuracy(),
            "altitude": location.altitude(),
            "altitude_accuracy": location.verticalAccuracy(),
            "course": location.course(),
            "speed": location.speed(),
            "timestamp": location.timestamp()
        }
    except Exception as e:
        # Fallback in case any property access fails
        return {
            "error": f"Error formatting location data: {str(e)}"
        }

def _get_error_info(error) -> Dict[str, Any]:
    """
    Extract useful error information from a CoreLocation error

    Args:
        error: CoreLocation error object or None

    Returns:
        Dict with error code and description
    """
    if not error:
        return {"code": 0, "description": "Unknown error"}

    error_code = error.code()
    error_desc = "Unknown error"

    if error_code == kCLErrorLocationUnknown:
        error_desc = "Unable to determine location"
    elif error_code == kCLErrorDenied:
        error_desc = "Location services access denied. Please enable in System Preferences."
    else:
        error_desc = f"Location services error {error_code}"

    return {"code": error_code, "description": error_desc}

@mcp.tool()
def get_current_location(use_cache: bool = True, timeout: int = 15,
                         accuracy: str = "best", polling_interval: float = 0.25) -> Dict[str, Any]:
    """
    Get the current geolocation on macOS

    Args:
        use_cache: Whether to use cached location if available and recent
        timeout: Maximum time in seconds to wait for location (1-30)
        accuracy: Desired accuracy level: 'best', 'navigation', 'ten_meters',
                  'hundred_meters', 'kilometer', or 'three_kilometers'
        polling_interval: Run loop interval in seconds (0.1-1.0)

    Returns:
        Dictionary with the following fields:
        - latitude: Latitude in degrees (float)
        - longitude: Longitude in degrees (float)
        - accuracy: Horizontal accuracy in meters (float)
        - altitude: Altitude in meters (float)
        - altitude_accuracy: Vertical accuracy in meters (float)
        - course: Direction of travel in degrees (float)
        - speed: Speed in meters per second (float)
        - timestamp: Time when the location was determined
        - error: Description of the error if one occurred
    """
    global _location_cache

    # Parameter validation
    timeout = min(max(1, timeout), 30)  # Limit timeout to 1-30 seconds
    polling_interval = min(max(0.1, polling_interval), 1.0)  # Limit to 0.1-1.0 seconds

    # Check cache first if enabled
    current_time = time.time()
    if use_cache and _location_cache["data"] and \
       current_time - _location_cache["timestamp"] < _location_cache["cache_duration"]:
        return _location_cache["data"]

    # Determine accuracy constant
    accuracy_map = {
        "best": kCLLocationAccuracyBest,
        "navigation": kCLLocationAccuracyBestForNavigation,
        "ten_meters": kCLLocationAccuracyNearestTenMeters,
        "hundred_meters": kCLLocationAccuracyHundredMeters,
        "kilometer": kCLLocationAccuracyKilometer,
        "three_kilometers": kCLLocationAccuracyThreeKilometers
    }
    desired_accuracy = accuracy_map.get(accuracy.lower(), kCLLocationAccuracyBest)

    # Create location manager and delegate
    manager = CLLocationManager.alloc().init()
    delegate = LocationDelegate.alloc().init()
    manager.setDelegate_(delegate)

    # Configure location manager
    manager.setDistanceFilter_(kCLDistanceFilterNone)
    manager.setDesiredAccuracy_(desired_accuracy)

    # Request authorization and start updating location
    manager.requestWhenInUseAuthorization()

    # Check if already denied - this can provide an early return
    auth_status = CLLocationManager.authorizationStatus()
    if auth_status == kCLAuthorizationStatusDenied:
        return {"error": _get_error_info(None)["description"]}

    manager.startUpdatingLocation()

    # Wait for location update or timeout
    start_time = time.time()
    while not delegate.is_updated and time.time() - start_time < timeout:
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(polling_interval))

    # Stop updating location
    manager.stopUpdatingLocation()

    # Handle errors
    if delegate.location_error or not delegate.location:
        error_info = _get_error_info(delegate.location_error)
        result = {"error": error_info["description"]}

        # Update cache with error result
        _location_cache["data"] = result
        _location_cache["timestamp"] = current_time

        return result

    # Extract and format location data
    result = _format_location_data(delegate.location)

    # Update cache
    _location_cache["data"] = result
    _location_cache["timestamp"] = current_time

    return result

@mcp.tool()
def clear_location_cache() -> Dict[str, str]:
    """
    Clear the location cache, forcing the next request to fetch fresh data

    Returns:
        Dictionary with status of the operation
    """
    global _location_cache
    _location_cache["data"] = None
    _location_cache["timestamp"] = 0
    return {"status": "cache_cleared"}

@mcp.tool()
def set_cache_duration(seconds: int = 30) -> Dict[str, int]:
    """
    Set the duration for which location data is considered valid

    Args:
        seconds: Number of seconds to cache location data (5-300)

    Returns:
        Dictionary with updated cache settings
    """
    global _location_cache
    _location_cache["cache_duration"] = max(5, min(seconds, 300))  # Limit to 5-300 seconds
    return {"cache_duration": _location_cache["cache_duration"]}

@mcp.tool()
def get_cache_status() -> Dict[str, Any]:
    """
    Get information about the current state of the location cache

    Returns:
        Dictionary with cache status information including time until expiration
    """
    global _location_cache

    current_time = time.time()
    time_since_update = current_time - _location_cache["timestamp"]
    has_data = _location_cache["data"] is not None

    return {
        "has_cached_data": has_data,
        "cache_duration": _location_cache["cache_duration"],
        "seconds_since_update": time_since_update if has_data else 0,
        "seconds_until_expiration": max(0, _location_cache["cache_duration"] - time_since_update) if has_data else 0,
        "is_expired": time_since_update > _location_cache["cache_duration"] if has_data else True
    }

@mcp.tool()
def get_location_async(callback_route: str = None, accuracy: str = "best") -> Dict[str, Any]:
    """
    Start an asynchronous location request that will call back to the specified route

    Args:
        callback_route: Route to call with the location data when available
        accuracy: Desired accuracy level ('best', 'navigation', etc.)

    Returns:
        Dictionary with status of the async request
    """
    if not callback_route:
        return {"error": "No callback_route specified"}

    import threading
    import requests
    from urllib.parse import urlparse

    # Validate callback_route format (basic check)
    try:
        parsed = urlparse(callback_route)
        if not all([parsed.scheme, parsed.netloc]):
            return {"error": "Invalid callback_route format. Must be a valid URL."}
    except:
        return {"error": "Invalid callback_route format"}

    def get_location_thread():
        try:
            # Get location with a shorter timeout for async requests
            result = get_current_location(use_cache=False, accuracy=accuracy, timeout=10)

            # Send result to callback URL
            try:
                requests.post(
                    callback_route,
                    json=result,
                    headers={"Content-Type": "application/json"},
                    timeout=5
                )
            except Exception as e:
                print(f"Error calling callback: {str(e)}")
        except Exception as e:
            print(f"Error in async location thread: {str(e)}")

    # Start thread for async processing
    thread = threading.Thread(target=get_location_thread)
    thread.daemon = True
    thread.start()

    return {
        "status": "location_request_started",
        "callback_route": callback_route,
        "accuracy": accuracy
    }

def main():
    """Entry point for the location command."""
    # Initialize and run the server
    mcp.run(transport='stdio')

if __name__ == "__main__":
    main()
