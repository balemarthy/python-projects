import random

NUM_DIGITS  = 3
MAX_GUESSES = 10

def main():
    print('''Bagels, A deductive logical game
     
      I am thinking of a {}-digit number with no repeated digits.
      Try to guess what it is. Here are some clues:

      When I say:                  That means:  
      Pico                         One digit is correct but in the wrong place
      Fermi                        One digit is correct and in the right place
      Bagels                       No digit is correct

      For example, if the secret number was 248 and your guess was 843, the clues would be
      Fermi Pico.'''.format(NUM_DIGITS))
    
    while True:  # Main game loop
        # This stores the secret number the player needs to guess:
        secretNum = getSecretNum()
        print('I have thought up a number')
        print('You have {} guesses to get it.'.format(MAX_GUESSES))
