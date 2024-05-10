import os, logging, io, re
from pathlib import Path

import xml.etree.ElementTree as ET
from xml.etree.ElementTree import Element
from defusedxml.ElementTree import parse

from lib.xml.disablexmlnamespace import DisableXmlNamespaces

class SecGenScenarioController(object):
    """
    Provides a means of interacting with scenario based behaviours.
    
    Allows prompts and interactions between the GPT4all to be controlled to provide
    a specific behaviour. 
    """
    sg_tree: ET
    root: Element
    isParsed = False
    bot_count = 0

    def parse_scenario(self, scenario_path):
        if Path(scenario_path).exists():
            p = Path(scenario_path)
            try:
                scenario = open(p, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None)
                with DisableXmlNamespaces():
                    try:
                        self.sg_tree = parse(scenario) # Use defusedxml for safe parsing
                        self.isParsed = True
                        self.set_root()
                        return True
                    except DefusedXmlException as ex:
                        logging.error(ex)
                        scenario.close()
                        return False
                    scenario.close()
                    return True
            except OSError as scenEx:
                scenario.close()
                print(scenEx)
                logging.error(scenEx)
                return False
        else:
            logging.error("Scenario path does not exist: " + scenario_path + "\n")
            print("Scenario not found exiting...")
            return False
        
        return False

    def set_root(self):
        self.root = self.sg_tree.getroot()

    def get_name(self):
        return self.root.find('name').text

    def get_channel(self):
        return self.root.find('channel').text

    def get_bots(self):
        return self.root.findall('bot')

    def get_all_bot_names(self):
        names = []
        for bot in self.get_bots():
            names.append(self.get_bot_name(bot))
        return names

    def get_bot_name(self, bot):
        return bot.find('name').text

    def get_bot_prompt(self, bot):
        return bot.find('prompt').text

    def get_prompt_items(self, bot):
        return bot.find("prompt_items").findall('item')

    def get_bot_expression(self, bot):
        return bot.find('expression').text

    def get_bot_contacts(self, bot):
        return bot.find('contacts').text

    def get_bot_task(self, bot):
        return bot.find('task').text

    def get_bot_protected(self, bot):
        return bot.find('protects')

    def map_prompt_items(self, bot):
        """
        Within the <prompt_items> extract all the item names and values if present
        """
        b_items = self.get_prompt_items(bot)
        items = []
        for item in b_items:
            name = item.find('name').text
            if item.find('value') != None:
                value = item.find('value').text
            else:
                value = ""
            items.append(dict(name = name, value = value))
        return items  

    def build_prompt(self, bot):
        """
        Create a dictionary from the <prompt> and extract the prompt template values
        and the prompt itself...
        """
        b_prompt = self.get_bot_prompt(bot)
        i_in_p = re.compile(r'\{(.*)\}')
        matches = i_in_p.findall(b_prompt)
        items = []

        for match in matches:
            items.append(match)

        pt = dict(input_variables = items, template = b_prompt)

        return pt