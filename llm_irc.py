import logging, sys, os, re, asyncio
from pathlib import Path
from threading import Thread

from irc.client_aio import AioSimpleIRCClient
import irc.client

from operator import itemgetter

from langchain_community.llms.gpt4all import GPT4All
from langchain.chains import ConversationChain, LLMChain
from langchain_core.prompt_values import PromptValue
from langchain_core.output_parsers import StrOutputParser
from langchain_text_splitters import CharacterTextSplitter
from langchain.prompts.prompt import PromptTemplate
from langchain.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain.chains.conversation.memory import ConversationBufferWindowMemory
from langchain_community.embeddings import GPT4AllEmbeddings
from langchain_core.runnables import RunnableLambda, RunnablePassthrough


class LLMClient():
    """
    Provides a connector to an IRC server

    https://python-irc.readthedocs.io/en/latest/irc.html#irc.client.Connection
    """
    model: GPT4All
    hasReplied = False

    def __init__(self, scenario, bot, model):
        self.scenario = scenario
        self.bot = bot
        self.name = scenario.get_bot_name(self.bot)
        self.model = model

        self.conversation = LLMChain(
            llm=self.model,
            prompt=PromptTemplate(
                input_variables=["usr_input"],
                template=scenario.get_bot_prompt(bot)
            ),
            verbose=True
        )

    def on_disconnect(self, connection, event):
        print("cya")

    def on_privmsg(self, connection, event):
        usr_msg: str = event.arguments[0]

        if usr_msg.find('public') != -1:
            print()

        if connection.nickname == self.name:
            response = self.get_response(usr_msg)
            if type(response) == list and len(response) >= 1:
                for res in response:
                    res = self.resp_stripper(res)
                    connection.privmsg(event.source, res)
            else:
                connection.privmsg(event.source, self.resp_stripper(response))

    def on_pubmsg(self, connection, event):
        usr_msg = event.arguments[0]
        if self.scenario.isParsed:
            if connection.nickname == self.name:
                response = self.get_response(usr_msg)
                if type(response) == list and len(response) >= 1:
                    for res in response:
                        res = self.resp_stripper(res)
                        if irc.client.is_channel(event.target):
                            if not self.hasReplied:
                                connection.privmsg(event.target, res)
                                self.hasReplied = True
                            self.hasReplied = False
                else:
                    if not self.hasReplied:
                        connection.privmsg(event.target, response.strip('\n\t\r'))
                        self.hasReplied = True
                    connection.reactor.loop.create_task(self.resp_sleep())
        else:
            connection.privmsg(event.source, "No Scenario loaded...")

    def get_response(self, usr_inp):
        """
        Gets a response from a model, splitting the response into smaller chunks, if it exceeds IRC's limit of 512 chars
        """
        chain = (
            {"usr_in": itemgetter("usr_in")}
            | self.conversation.prompt
            | self.model
            | StrOutputParser()
        )
        response = chain.invoke({"usr_in": usr_inp})
        clean_res = self.resp_stripper(response)

        if len(clean_res.encode('utf-8')) >= 500:
            text_splitter = CharacterTextSplitter(
                separator=".", chunk_size=500, chunk_overlap=50, length_function=len, is_separator_regex=False
            )
            clean_res = text_splitter.split_text(response)
            for res in clean_res: 
                res = self.resp_stripper(res)
        return clean_res

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

    async def resp_sleep(self):
        await asyncio.sleep(2)
        self.hasReplied=False