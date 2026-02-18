# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter


class WalmartScraperPipeline:
    def process_item(self, item, spider):
        spider.logger.info('Pipeline received item link=%s incomplete=%s name=%s price=%s', item.get('link'), item.get('incomplete'), item.get('name'), item.get('price'))
        return item
