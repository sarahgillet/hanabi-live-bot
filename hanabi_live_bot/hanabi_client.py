# Imports (standard library)
import json

# Imports (3rd-party)
import websocket

# Imports (local application)
from hanabi_live_bot.constants import ACTION
from hanabi_live_bot.game_state import GameState
from hanabi_live_bot.constants import MAX_CLUE_NUM
import traceback

class HanabiClient:
    def __init__(self, url, cookie):
        # Initialize all class variables
        self.commandHandlers = {}
        self.tables = {}
        self.username = ''
        self.ws = None
        self.games = {}

        # Initialize the Hanabi Live command handlers (for the lobby)
        self.commandHandlers['welcome'] = self.welcome
        self.commandHandlers['warning'] = self.warning
        self.commandHandlers['error'] = self.error
        self.commandHandlers['chat'] = self.chat
        self.commandHandlers['table'] = self.table
        self.commandHandlers['tableList'] = self.table_list
        self.commandHandlers['tableGone'] = self.table_gone
        self.commandHandlers['tableStart'] = self.table_start

        # Initialize the Hanabi Live command handlers (for the game)
        self.commandHandlers['init'] = self.init
        self.commandHandlers['gameAction'] = self.game_action
        self.commandHandlers['gameActionList'] = self.game_action_list
        self.commandHandlers['yourTurn'] = self.your_turn
        self.commandHandlers['databaseID'] = self.database_id

        # Start the WebSocket client
        print('Connecting to "' + url + '".')

        self.ws = websocket.WebSocketApp(
            url,
            on_message=lambda ws, message: self.websocket_message(ws, message),
            on_error=lambda ws, error: self.websocket_error(ws, error),
            on_open=lambda ws: self.websocket_open(ws),
            on_close=lambda ws: self.websocket_close(ws),
            cookie=cookie,
        )

    # ------------------
    # WebSocket Handlers
    # ------------------

    def websocket_message(self, ws, message):
        # WebSocket messages from the server come in the format of:
        # commandName {"data1":"data2"}
        # For more information, see:
        # https://github.com/Zamiell/hanabi-live/blob/master/src/websocketMessage.go
        result = message.split(' ', 1)  # Split it into two things
        if len(result) != 1 and len(result) != 2:
            print('error: recieved an invalid WebSocket message:')
            print(message)
            return

        command = result[0]
        try:
            data = json.loads(result[1])
        except:
            print('error: the JSON data for the command of "' + command +
                  '" was invalid')
            return

        if command in self.commandHandlers:
            print('debug: got command "' + command + '"')
            try:
                self.commandHandlers[command](data)
            except Exception as e:
                print('error: command handler for "' + command + '" failed:',
                      e, traceback.format_exc())
                return
        else:
            print('debug: ignoring command "' + command + '"')

    def websocket_error(self, ws, error):
        print('Encountered a WebSocket error:', error)

    def websocket_close(self, ws):
        print('WebSocket connection closed.')

    def websocket_open(self, ws):
        print('Successfully established WebSocket connection.')

    def start_server(self):
        self.ws.run_forever()

    # ------------------------------------
    # Hanabi Live Command Handlers (Lobby)
    # ------------------------------------

    def welcome(self, data):
        # The "welcome" message is the first message that the server sends us
        # once we have established a connection
        # It contains our username, settings, and so forth
        self.username = data['username']

    def error(self, data):
        # Either we have done something wrong,
        # or something has gone wrong on the server
        print(data)

    def warning(self, data):
        # We have done something wrong
        print(data)

    def chat(self, data):
        # We only care about private messages
        if data['recipient'] != self.username:
            return

        # We only care about private messages that start with a forward slash
        if not data['msg'].startswith('/'):
            return
        data['msg'] = data['msg'][1:]  # Remove the slash

        # We want to split it into two things
        result = data['msg'].split(' ', 1)
        command = result[0]

        if command == 'join':
            self.chat_join(data)
        else:
            self.chat_reply('That is not a valid command.', data['who'])

    def chat_join(self, data):
        # Someone sent a private message to the bot and requested that we join
        # their game
        # Find the table that the current user is currently in
        table_id = None
        for table in self.tables.values():
            # Ignore games that have already started (and shared replays)
            if table['running']:
                continue

            if data['who'] in table['players']:
                if len(table['players']) == 6:
                    msg = ('Your game is full. Please make room for me before '
                           'requesting that I join your game.')
                    self.chat_reply(msg, data['who'])
                    return

                table_id = table['id']
                break

        if table_id is None:
            self.chat_reply(
                'Please create a table first before requesting '
                'that I join your game.', data['who'])
            return
        result = data['msg'].split(' ', 1)
        self.send('tableJoin', {
            'tableID': table_id,
            'password': result[1]
        })

    def table(self, data):
        self.tables[data['id']] = data

    def table_list(self, data_list):
        for data in data_list:
            self.table(data)

    def table_gone(self, data):
        del self.tables[data['id']]

    def table_start(self, data):
        # The server has told us that a game that we are in is starting
        # So, the next step is to request some high-level information about the
        # game (e.g. number of players)
        # The server will respond with an "init" command
        self.send('getGameInfo1', {
            'tableID': data['tableID'],
        })

    # -----------------------------------
    # Hanabi Live Command Handlers (Game)
    # -----------------------------------

    def init(self, data):
        # At the beginning of the game, the server sends us some high-level
        # data about the game, including the names and ordering of the players
        # at the table

        # Make a new game state and store it on the "games" dictionary
        state = GameState()
        self.games[data['tableID']] = state

        state.players = data['names']

        # Find our index
        for i in range(len(state.players)):
            player_name = state.players[i]
            if player_name == self.username:
                state.our_index = i
                break

        # Initialize the hands for each player (an array of cards)
        for i in range(len(state.players)):
            state.hands.append([])

        # Initialize the play stacks
        '''
        This is hard coded to 5 because there 5 suits in a no variant game
        Hanabi Live supports variants that have 3, 4, and 6 suits
        TODO This code should compare "data['variant']" to the "variants.json"
        file in order to determine the correct amount of suits
        https://raw.githubusercontent.com/Zamiell/hanabi-live/master/public/js/src/data/variants.json
        '''
        for i in range(5):
            state.play_stacks.append([])
        
        for i in range(5):
            state.discard_pile.append({1:[],2:[],3:[],4:[],5:[]})
        

        # At this point, the JavaScript client would have enough information to
        # load and display the game UI; for our purposes, we do not need to
        # load a UI, so we can just jump directly to the next step
        # Now, we request the specific actions that have taken place thus far
        # in the game
        self.send('getGameInfo2', {
            'tableID': data['tableID'],
        })

    def game_action(self, data):
        # We just recieved a new action for an ongoing game
        self.handle_action(data['action'], data['tableID'])

    def game_action_list(self, data):
        # We just recieved a list of all of the actions that have occurred thus
        # far in the game
        for action in data['list']:
            self.handle_action(action, data['tableID'])

    def handle_action(self, data, table_id):
        print('debug: got a game action of "' + data['type'] + '" for table ' +
              str(table_id))


        # Local variables
        state = self.games[table_id]

        if data['type'] == 'draw':
            # Add the newly drawn card to the player's hand
            hand = state.hands[data['who']]
            hand.append({
                'order': data['order'],
                'suit': data['suit'],
                'rank': data['rank'],
                'knowledge': [1]*25,
                'clue':[ [0]*5, [0]*5]
            })
            # every time we draw a card the deck has one less
            state.num_cards_deck -= 1
            print(state.num_cards_deck)

        elif data['type'] == 'play':
            seat = data['which']['index']
            order = data['which']['order']
            card, index = self.remove_card_from_hand(state, seat, order)
            if card is not None:
                state.play_stacks[card['suit']].append(card) # TODO Add the card to the play stacks
                card['hand_index'] = index
                print(state.play_stacks)
                pass
            state.last_action = data.copy()
            state.last_action['who'] = state.current_turn

        elif data['type'] == 'discard':
            seat = data['which']['index']
            order = data['which']['order']
            card, index = self.remove_card_from_hand(state, seat, order)
            if card is not None:
                # TODO better representation so that vecotrizing easier
                state.discard_pile[data['which']['suit']][data['which']['rank']].append(card)
                card['hand_index'] = index
                print(state.discard_pile)
                pass

            # Discarding adds a clue
            if not data['failed']:  # Misplays are represented as discards
                state.clue_tokens += 1
                state.clue_tokens = min(state.clue_tokens, MAX_CLUE_NUM)
                state.last_action = data
                state.last_action['who'] = state.current_turn

        elif data['type'] == 'clue':
            # Each clue costs one clue token
            state.clue_tokens -= 1
            state.last_action = data.copy()
            state.last_action['who'] = state.current_turn
            hand = state.hands[data['target']]
            listClues = data['list']
            for card in hand:
                if card['order'] in listClues:
                    # note clue gotten
                    adjustIndex = 0
                    if data['clue']['type'] == 1:
                        adjustIndex = 1
                    card['clue'][data['clue']['type']][data['clue']['value']-adjustIndex]=1
                    #transform to card knowledge: vector of all possible interpretations of card
                    intermediateCardKnowledge = [0]*25
                    for rank in range(5):
                        for color in range(5):
                            if ((data['clue']['type'] == 0 and color == data['clue']['value']) or
                                (data['clue']['type'] == 1 and rank == data['clue']['value']-1)):
                                intermediateCardKnowledge[color*5+rank] = 1
                    card['knowledge'] = [a and b for a,b in zip(card['knowledge'], intermediateCardKnowledge)]
                else:
                    # clues give information about other cards that did not receive the clue
                    intermediateCardKnowledge = [1]*25
                    for rank in range(5):
                        for color in range(5):
                            if ((data['clue']['type'] == 0 and color == data['clue']['value']) or
                                (data['clue']['type'] == 1 and rank == data['clue']['value']-1)):
                                intermediateCardKnowledge[color*5+rank] = 0
                    card['knowledge'] = [a and b for a,b in zip(card['knowledge'], intermediateCardKnowledge)]

        elif data['type'] == 'turn':
            state.turn = data['num']
            state.current_turn = data['who']
        elif data['type'] == 'strike':
            state.life_tokens -= 1
            state.last_action = data.copy()
            state.last_action['who'] = state.current_turn

    def your_turn(self, data):
        # The "yourTurn" command is only sent when it is our turn
        # (in the present, as opposed to recieving a "game_action" message
        # about a turn in the past)
        # Query the AI functions to see what to do
        self.decide_action(data['tableID'])

    def database_id(self, data):
        # Games are transformed into shared replays after they are copmleted
        # The server sends a "databaseID" message when the game has ended
        # Use this as a signal to leave the shared replay
        self.send('tableUnattend', {
            'tableID': data['tableID'],
        })

        # Delete the game state for the game to free up memory
        del self.games[data['tableID']]

    # ------------
    # AI functions
    # ------------

    def decide_action(self, table_id):
        # Local variables
        state = self.games[table_id]

        # The server expects to be told about actions in the following format:
        # https://github.com/Zamiell/hanabi-live/blob/master/src/command_action.go

        # Decide what to do
        if state.clue_tokens > 0:
            # There is a clue available,
            # so give a rank clue to the next person's slot 1 card

            # Target the next player
            target_index = state.our_index + 1
            if target_index > len(state.players) - 1:
                target_index = 0

            # Cards are added oldest to newest,
            # so "slot 1" is the final element in the list
            target_hand = state.hands[target_index]
            slot_1_card = target_hand[-1]

            self.send(
                'action', {
                    'tableID': table_id,
                    'type': ACTION.RANK_CLUE,
                    'target': target_index,
                    'value': slot_1_card['rank'],
                })
        else:
            # There are no clues available, so discard our oldest card
            oldest_card = state.hands[state.our_index][0]
            self.send(
                'action', {
                    'tableID': table_id,
                    'type': ACTION.DISCARD,
                    'target': oldest_card['order'],
                })

    # -----------
    # Subroutines
    # -----------

    def chat_reply(self, message, recipient):
        self.send('chatPM', {
            'msg': message,
            'recipient': recipient,
            'room': 'lobby',
        })

    def send(self, command, data):
        if not isinstance(data, dict):
            data = {}
        self.ws.send(command + ' ' + json.dumps(data))
        print('debug: sent command "' + command + ' ' + str(data) +'"')

    def findCardIndex(self, hand, order):
        card_index = -1
        for i in range(len(hand)):
            card = hand[i]
            if card['order'] == order:
                card_index = i 
        return card_index  

    # "seat" is the index of the player
    def remove_card_from_hand(self, state, seat, order):
        hand = state.hands[seat]
        card_index = self.findCardIndex(hand, order)
        if card_index == -1:
            print('error: unable to find card with order ' + str(order) + ' in'
                  'the hand of player ' + str(seat))
            return None
        card = hand[card_index]
        del hand[card_index]
        return card,card_index

