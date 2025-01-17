import scrapy

from locations.dict_parser import DictParser
from locations.geo import postal_regions
from locations.spiders.century_21 import Century21Spider


class Century21FrSpider(scrapy.Spider):
    name = "century_21_fr"
    item_attributes = Century21Spider.item_attributes
    allowed_domains = ["century21.fr"]
    custom_settings = {"ROBOTSTXT_OBEY": False}

    def start_requests(self):
        for record in postal_regions("FR"):
            template_url = "https://www.century21.fr/autocomplete/localite/?q={}"
            yield scrapy.Request(template_url.format(record["postal_region"]))

    def parse(self, response):
        for data in response.json():
            item = DictParser.parse(data)
            item["postcode"] = data.get("cp")

            yield item
