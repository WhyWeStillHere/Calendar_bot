import datetime
from googleapiclient.discovery import build
from oauth2client.client import OAuth2WebServerFlow, FlowExchangeError
from oauth2client.file import Storage
import httplib2
import sys
import os
from app import bot, SCOPES
import logging


def get_credentials(chat_id):
    # Get credentials from file
    storage = Storage('./credentials/credentials-{}.dat'.format(chat_id))
    return storage.get()
        

def save_credentials(chat_id, credentials):
    # Save credentials to file
    storage = Storage('./credentials/credentials-{}.dat'.format(chat_id))
    storage.put(credentials)


def refresh_get_credentials(chat_id):
    # Get old credentials
    credentials = get_credentials(chat_id)
    if credentials is None:
        return None
    # Refresh access token for credentials
    credentials.refresh(httplib2.Http())
    return credentials


@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.send_message(message.chat.id, 'Hi! Firstly, you need to log in\nSend /reg command\n'
                                      'After registration send /help to get list of available commands')


@bot.message_handler(commands=['help'])
def handle_help(message):
    if get_credentials(message.chat.id) is None:
        bot.send_message(message.chat.id, 'Firstly, you need to log in\nSend /reg command')
        return
    bot.send_message(message.chat.id, 'List of available commands\n'
                                      '/near "n"\n  Send list of "n" nearest commands\n  0 < "n" <= 100\n'
                                      '/delete\n  Delete your authentication info')


@bot.message_handler(commands=['delete'])
def handle_reg_message(message):
    try:
        if get_credentials(message.chat.id) is None:
            bot.send_message(message.chat.id, 'Credentials are do not exist')
            return
        os.remove('./credentials/credentials-{}.dat'.format(message.chat.id))
        bot.send_message(message.chat.id, 'Your credentials are deleted')
    except Exception:
        logging.error(sys.exc_info())


@bot.message_handler(commands=['reg'])
def handle_reg_message(message):
    try:

        if get_credentials(message.chat.id) is not None:
            bot.send_message(message.chat.id, 'You are already log in\n'
                                              'Send /help to get list of available commands')
            return
        bot.send_message(message.chat.id, 'Starting authentication')
        flow = OAuth2WebServerFlow(client_id='494153107501-dkfmr8sc3k1pcsmo4q5bu2v7rnvg0a8m.apps.googleusercontent.com',
                                   client_secret='DLY0IgUVy1Q6bTGXR5wJ4-nn',
                                   scope=SCOPES, redirect_uri='urn:ietf:wg:oauth:2.0:oob')
        # Getting authentication url
        auth_url = flow.step1_get_authorize_url()
        bot.send_message(message.chat.id, '{} - Authorization_url'.format(auth_url))
        bot.send_message(message.chat.id, 'Write here your authentication token')
        # Receive message with auth code
        bot.register_next_step_handler(message, lambda m: get_auth_token(m, flow))
    except Exception:
        bot.send_message(message.chat.id, 'Unknown error')
        logging.error(sys.exc_info())  # Make logging


def get_auth_token(message, flow):
    try:
        # Get auth code from message
        code = message.text
        # Get credentials from google server
        credentials = flow.step2_exchange(code)
        # Save credentials to the file
        save_credentials(message.chat.id, credentials)
        bot.send_message(message.chat.id, 'End of authentication')
    except Exception as err:
        if isinstance(err, FlowExchangeError):
            bot.send_message(message.chat.id, 'Incorrect authentication code')
        else:
            bot.send_message(message.chat.id, 'Unknown error')
            logging.error(sys.exc_info())  # Make logging


@bot.message_handler(commands=['near'])
def upcoming_events(message):
    try:
        credentials = refresh_get_credentials(message.chat.id)
        if credentials is None:
            bot.send_message(message.chat.id, 'You need to log in first\nSend /reg command')
            return
        try:
            number_of_events = int(message.text[5:])
        except ValueError:
            bot.send_message(message.chat.id, 'Incorrect number, you should write only a number')
            return
        if number_of_events <= 0:
            bot.send_message(message.chat.id, 'Incorrect number of events')
            return
        if number_of_events > 100:
            bot.send_message(message.chat.id, 'Too much events')
            return
        # Launch calendar API interactor
        service = build('calendar', 'v3', credentials=credentials)
        # Call the Calendar API
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        # 'Z' indicates UTC time
        bot.send_message(message.chat.id, 'Getting {} upcoming events'.format(number_of_events))
        events_result = service.events().list(calendarId='primary', timeMin=now,
                                              maxResults=number_of_events, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])
        events_text = []
        if not events:
            events_text.append('No upcoming events found.')
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            events_text.append('{} {}'.format(start, event['summary']))
        bot.send_message(message.chat.id, '\n'.join(events_text))
    except Exception:
        bot.send_message(message.chat.id, 'Unknown error')
        logging.error(sys.exc_info())  # Make logging
