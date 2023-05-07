import csv
import json
from math import sqrt
import numpy as np
import scrapy

from locations.items import GeojsonPointItem
from math import sqrt

HEADERS = {"X-Requested-With": "XMLHttpRequest"}
STORELOCATOR = "https://www.starbucks.com/bff/locations?lat={}&lng={}"


class StarbucksSpider(scrapy.Spider):
    name = "starbucks"
    item_attributes = {"brand": "Starbucks", "brand_wikidata": "Q37158", "extras": Categories.COFFEE_SHOP.value}
    allowed_domains = ["www.starbucks.com"]

    def start_requests(self):
        searchable_point_files = [
            "./locations/searchable_points/us_centroids_50mile_radius.csv",
            "./locations/searchable_points/ca_centroids_50mile_radius.csv",
        ]

        for point_file in searchable_point_files:
            with open(point_file) as points:
                reader = csv.DictReader(points)
                for point in reader:
                    request = scrapy.Request(
                        url=STORELOCATOR.format(point["latitude"], point["longitude"]),
                        headers=HEADERS,
                        callback=self.parse,
                    )
                    # Distance is in degrees...
                    request.meta["distance"] = 1
                    yield request

    def parse(self, response):
        responseJson = json.loads(response.body)
        stores = responseJson["stores"]

        for store in stores:
            storeLat = store["coordinates"]["latitude"]
            storeLon = store["coordinates"]["longitude"]
            properties = {
                "name": store["name"],
                "street_address": ", ".join(
                    filter(
                        None,
                        [
                            store["address"]["streetAddressLine1"],
                            store["address"]["streetAddressLine2"],
                            store["address"]["streetAddressLine3"],
                        ],
                    )
                ),
                "city": store["address"]["city"],
                "state": store["address"]["countrySubdivisionCode"],
                "country": store["address"]["countryCode"],
                "postcode": store["address"]["postalCode"],
                "phone": store["phoneNumber"],
                "ref": store["id"],
                "lon": storeLon,
                "lat": storeLat,
                "brand": store["brandName"],
                "website": f'https://www.starbucks.com/store-locator/store/{store["id"]}/{store["slug"]}',
                "extras": {"number": store["storeNumber"], "ownership_type": store["ownershipTypeCode"]},
            }
            yield Feature(**properties)

        # Get lat and lng from URL
        pairs = response.url.split("?")[-1].split("&")
        # Center is lng, lat
        center = [float(pairs[1].split("=")[1]), float(pairs[0].split("=")[1])]

        paging = responseJson["paging"]
        if paging["returned"] > 0 and paging["limit"] == paging["returned"]:
            if response.meta["distance"] > 0.15:
                nextDistance = response.meta["distance"] / 2
                # Create eight new coordinate pairs
                nextCoordinates = [
                    [center[0] - nextDistance, center[1] + nextDistance],
                    [center[0] + nextDistance, center[1] + nextDistance],
                    [center[0] - nextDistance, center[1] - nextDistance],
                    [center[0] + nextDistance, center[1] - nextDistance],
                ]
                urls = [STORELOCATOR.format(c[1], c[0]) for c in nextCoordinates]
                for url in urls:
                    request = scrapy.Request(url=url, headers=HEADERS, callback=self.parse)
                    request.meta["distance"] = nextDistance
                    yield request

            elif response.meta["distance"] > 0.10:
                # Only used to track how often this happens
                self.logger.info("Using secondary search of far away stores")
                nextDistance = response.meta["distance"] / 2 

                nextCoordinates = []
                current_center = center
                additional_stores = 5
                distances_array = np.full((len(stores), additional_stores), np.nan)

                # Loop through to find 5 more stores
                for ii in range(additional_stores):

                    # Find distance between current center and all stores
                    for jj, store in enumerate(stores): 
                        store_lat = store["coordinates"]["latitude"]
                        store_lon = store["coordinates"]["longitude"]
                        distances_array[jj,ii] = sqrt((current_center[1] - store_lat)**2 + (current_center[0] - store_lon)**2)

                    # Find mean distance each store and center/new search coords 
                    mean_distances = np.nanmean(distances_array, 1)

                    # Find store furthest away
                    max_store = np.argmax(mean_distances)

                    # Replace current center
                    current_center = [stores[max_store]["coordinates"]["longitude"], 
                                      stores[max_store]["coordinates"]["latitude"]]
                    
                    # Append it to the next search list
                    nextCoordinates.append([stores[max_store]["coordinates"]["longitude"], 
                                      stores[max_store]["coordinates"]["latitude"]])
                urls = [STORELOCATOR.format(c[1], c[0]) for c in nextCoordinates]
                for url in urls:
                    self.logger.info("Adding %s to list", url)

                    request = scrapy.Request(url=url, headers=HEADERS, callback=self.parse)
                    request.meta["distance"] = nextDistance
                    yield request
