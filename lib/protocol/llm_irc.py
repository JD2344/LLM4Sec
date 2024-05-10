import logging, sys, os, re, asyncio, time
from pathlib import Path
from threading import Thread

from irc.client import SimpleIRCClient
from irc.client_aio import AioSimpleIRCClient
import irc.client

from operator import itemgetter

from langchain_core.prompt_values import PromptValue
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, MessagesPlaceholder
from langchain.prompts.prompt import PromptTemplate
from langchain_core.prompt_values import ChatPromptValue
from langchain_text_splitters import CharacterTextSplitter
from langchain.chains.conversation.base import ConversationChain
from langchain.chains.conversation.memory import ConversationBufferWindowMemory
from langchain.memory.summary import ConversationSummaryMemory
from langchain.output_parsers.json import SimpleJsonOutputParser
from langchain_community.llms.gpt4all import GPT4All
from langchain_community.chat_message_histories import SQLChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_experimental.text_splitter import SemanticChunker
from langchain_community.embeddings import GPT4AllEmbeddings


class LLMClient(AioSimpleIRCClient):
    """
    Provides a connector to an IRC server

    https://python-irc.readthedocs.io/en/latest/irc.html#irc.client.Connection
    """
    model: GPT4All
    hasReplied = False
    msg_count = 0
    SQLITE_DB = "sqlite:///chat_history.db"

    def __init__(self, scenario, bot, model):
        irc.client.SimpleIRCClient.__init__(self)
        self.scenario = scenario
        self.bot = bot
        self.name = scenario.get_bot_name(bot)
        self.model = model
        self.chain_vals = self.build_chain_vals()
        self.bp = scenario.build_prompt(bot)
        self.prompt = PromptTemplate.from_template(self.bp["template"])
        self.session_id = scenario.get_bot_name(bot) + " " + scenario.get_name()

    def on_disconnect(self, connection, event):
        connection.privmsg("#"+self.scenario.get_channel(), "Something went wrong... Bye!")

    def on_welcome(self, connection, event):
        """
        Check if a timer should be started to invoke a few private message exchanges.
        """
        print("hi")

    def on_privmsg(self, connection, event):
        usr_msg = event.arguments[0]

        if self.scenario.isParsed:
            if event.source.find(self.name) == -1:
                response = self.get_response(usr_msg)
                self.res_handler(connection, event, response)
        else:
            response = self.get_response(usr_msg)
            self.res_handler(connection, event, response)

    def on_pubmsg(self, connection, event):
        usr_msg = event.arguments[0]
        
        if self.scenario.isParsed:
            if len(self.scenario.get_bots()) == 1:
                response = self.get_response(usr_msg)
                self.res_handler(connection, event, response)
            else:
                names = self.scenario.get_all_bot_names()
                isbot = any(name in event.source for name in names)
                # Check if a bot is responding
                if not isbot:
                    response = self.get_response(usr_msg)
                    self.res_handler(connection, event, response)
        else:
            response = self.get_response(usr_msg)
            self.res_handler(connection, event, response)
                
    def get_response(self, usr_inp):
        """
        Gets a response from a model
        """
        prompt = PromptTemplate(
            template=self.bp["template"],
            input_variables=self.bp['input_variables']
        )
        
        chain = (
            self.chain_vals['cp_val']
            | prompt
            | self.model
            | StrOutputParser()
        )

        self.chain_vals['ci_val']['usr_in']= usr_inp
        response = chain.invoke(self.chain_vals['ci_val'])
        clean_res = self.resp_stripper(response)
        clean_res = self.tidy_response(clean_res)
                          
        return clean_res

    def tidy_response(self, response):
        """
        Responsible for checking a message size prior to sending over IRC. 
        512 Bytes is too long for IRC to handle, so we need to split the responses up.
        """
        if len(response.encode('utf-8')) >= 480:
            text_splitter = CharacterTextSplitter(
                separator=".", chunk_size=450, chunk_overlap=50, length_function=len, is_separator_regex=False
            )
            clean_res = text_splitter.split_text(response)

            for res in clean_res: 
                res = self.resp_stripper(res)
            
            return clean_res
        else:
            return response
        
    def resp_stripper(self, response) -> str:
        """
        Checks a given response and sanitizes. It removed carriage returns, newlines and tabs. 
        This cleans it up before transmitting over IRC.
        """
        model_resp = ""
        for token in response:
            token = token.lstrip("\n\t\r")
            token = token.replace("\n", "", -1)
            token = token.strip("\n\t\r")
            model_resp += token
        return model_resp

    def build_chain_vals(self):
        """
        Generate two differing dictionaries for model invoking
        The first contains all the item_getters for the Output parser
        {"item": itemgetter(item), "item2": itemgetter(item2)}
        The second contains the value and keys for model invocation
        {"item": val, "item2": val}

        As a standard - usr_in will ALWAYS be present and not have value,
        It gets mutated later as it needs changing to a user controlled value.
        """
        items = self.scenario.map_prompt_items(self.bot)
        out = {}
        chain_p = {}
        chain_in = {}
        for item in items:
            if item["value"] == '':
                ci_val = item['name']
                cp_val = itemgetter(item['name'])
            else:
                ci_val = item['value']
                cp_val = itemgetter(item['name'])
            chain_in[item['name']] = ci_val
            chain_p[item['name']] = cp_val
            out['ci_val'] = chain_in
            out['cp_val'] = chain_p

        return out
        
    def res_handler(self, connection, event, cleaned_res):
        if type(cleaned_res) == list and len(cleaned_res) > 1:
            if not self.hasReplied and self.scenario.bot_count > 1:
                for res in cleaned_res:
                    res = self.resp_stripper(res)
                    self.send_to_target(connection, event, res)
                self.hasReplied = True
                connection.reactor.loop.create_task(self.resp_sleep())
            else:
                if self.scenario.bot_count == 1:
                    for res in cleaned_res:
                        res = self.resp_stripper(res)
                        self.send_to_target(connection, event, res)
        else:
            if not self.hasReplied and self.scenario.bot_count > 1:
                self.send_to_target(connection, event, cleaned_res)
                self.hasReplied = True
                connection.reactor.loop.create_task(self.resp_sleep())
            else:
                connection.privmsg(event.target, cleaned_res)

    def send_to_target(self, connection, event, msg):
        if irc.client.is_channel(event.target):
            connection.privmsg(event.target, msg)
        else:
            connection.privmsg(event.source, msg)

    async def resp_sleep(self):
        """
        Makes a sleep task occur, good for when there are multiple bots as it prevents loops 
        if infinite replies that cannot be stopped. 
        """
        await asyncio.sleep(3)
        self.hasReplied=False