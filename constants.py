# Client constants must match the server constants:
# https://github.com/Zamiell/hanabi-live/blob/master/src/constants.go


class ACTION():
    PLAY = 0
    DISCARD = 1
    COLOR_CLUE = 2
    RANK_CLUE = 3


# The maximum amount of clues
# (and the amount of clues that players start the game with)
MAX_CLUE_NUM = 8
MAX_DECK = 50
MAX_TOKENS = 3
HAND_SIZE = 5
