import os, logging, io
from pathlib import Path

import subprocess

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

    def __init__(self, scenario_path):
        self.isParsed = self.parse_scenario(scenario_path)
        self.set_root()

    def parse_scenario(self, scenario_path):
        if Path(scenario_path).exists():
            p = Path(scenario_path)
            try:
                scenario = open(p, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None)
                with DisableXmlNamespaces():
                    try:
                        self.sg_tree = parse(scenario) # Use defusedxml for safe parsing
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

    def get_channel(self):
        return self.root.find('channel').text

    def get_bots(self):
        return self.root.findall('bot')

    def get_bot_name(self, bot):
        return bot.find('name').text

    def get_bot_prompt(self, bot):
        return bot.find('prompt').text