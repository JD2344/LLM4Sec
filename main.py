#!/usr/bin/env python
import logging, argparse, sys, os, asyncio

import irc
from irc.client_aio import AioReactor, Reactor

from langchain_community.llms.gpt4all import GPT4All

from lib.protocol.llm_irc import LLMClient
from lib.xml.scen_parser import SecGenScenarioController

logging.basicConfig(filename='logs/debug.log', filemode='w', format='%(asctime)s %(message)s',
                    encoding='utf-8', level=logging.DEBUG)

def create_connections(loop, sp, irc_handler, model):
    bots = sp.get_bots()
    for bot in bots:
        try:
            c = loop.run_until_complete(
                irc_handler.server().connect(
                    "localhost", 6667, sp.get_bot_name(bot)
                )
            )
            llmc = LLMClient(sp, bot, model)
            c.add_global_handler("privmsg", llmc.on_privmsg)
            c.add_global_handler("disconnect", llmc.on_disconnect)
            if bot.find("SIP") != None:
                c.add_global_handler("pubmsg", llmc.on_pubmsg)
        except irc.client.ServerConnectionError:
            print(sys.exc_info()[1])
            raise SystemExit(1) from None

def main():
    parser = argparse.ArgumentParser(description="GPT4Sec options:", add_help=True)
    parser.add_argument('-r', '--run', action='store_true', required=True, help="Run GPT4Sec")
    parser.add_argument('-m', '--model', default="mistral-7b-instruct-v0.1.Q4_0.gguf", type=str, help="The model to use")
    parser.add_argument('-p', '--model_path', default="/home/vagrant/.cache/", type=str, help="Defaults to $HOME/.cache on linux")
    parser.add_argument('-s', '--scenario', type=str, help="The scenario path")
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-d', '--device', choices=['gpu', 'cpu'], help="Whether to use GPU or CPU")
    group.add_argument('-t', '--threads', default=1, help="How many CPU threads to use")
    parser.add_argument('-ps', '--printstream', action='store_true', default=False, help="Should generation stream to output")
    parser.add_argument('-dm', '--download', action='store_true', default=False, help="Whether to download the model")

    if len(sys.argv)==1:
        parser.print_help()
        parser.exit()

    try:
        args = parser.parse_args()
    except:
        logging.critical("The following exception occured: \n")
        exit()

    if args.run:
        if args.scenario:
            sp = SecGenScenarioController()
            isParsed = sp.parse_scenario(args.scenario)

            if isParsed:
                sp.bot_count = len(sp.get_bots())
                llm = GPT4All(model=args.model, allow_download=args.download, n_threads=args.threads, device=args.device, streaming=args.printstream)
                loop = asyncio.new_event_loop()
                irc_handler = AioReactor(loop=loop)

                server = irc_handler.server()
                create_connections(loop, sp, irc_handler, llm)
                if sp.isParsed:
                    for connection in irc_handler.connections:
                        if connection.connected:
                            connection.join("#"+sp.get_channel(), connection.username)

                try:
                    irc_handler.process_forever()
                finally:
                    loop.close()
            else:
                print("Scenario Unable to be parsed, please check the scenario exists and is valid")
        else:
            print("No scenario provided...")

if __name__ == "__main__":
    main()