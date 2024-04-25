import pygame
import sys
import requests
import json
import yaml
import argparse
import re
from typing import List, Dict, Any, Iterator, Tuple
from colorama import Fore, init

# Initialize colorama for terminal color reset
init(autoreset=True)

# Initialize pygame
pygame.init()


class GameConfig:
    def __init__(self, story_path: str):
        self.width, self.height = 1470, 956
        self.font_path = "fonts/the-neverending-story.ttf"
        self.font_size = 24
        self.font = pygame.font.Font(self.font_path, self.font_size)
        self.line_height = self.font.get_height() + 5
        self.colors = {
            'black': (0, 0, 0),
            'green': (0, 255, 0),
            'blue': (0, 0, 255),
            'red': (255, 0, 0),
        }
        self.load_config(story_path)

    def load_config(self, path: str):
        try:
            with open(path, 'r') as f:
                config = yaml.safe_load(f)
            self.model = config.get('model', 'llama2')
            self.ollama_url = config.get('ollama_url', 'http://localhost:11434')
            self.num_ctx = config.get('num_tokens', 4096)
            self.temperature = config.get('temperature', 0.5)
            self.player_card = config.get('player_card')
            self.companion_cards = config.get('companion_cards', [])
            self.story_card = config.get('story_card')
        except FileNotFoundError:
            print(Fore.RED + "Story file not found.")
            sys.exit(1)
        except yaml.YAMLError as exc:
            print(Fore.RED + f"Error parsing YAML file: {exc}")
            sys.exit(1)


class Game:
    def __init__(self, config: GameConfig):
        self.config = config
        self.screen = pygame.display.set_mode(
            (self.config.width, self.config.height)
        )
        pygame.display.set_caption("Text Adventure Game")
        self.messages = []
        self.display_messages = []
        self.is_story_update = False

    def run(self):
        clock = pygame.time.Clock()
        input_text = ''

        base_y = 10
        text_generator = None
        next_word_time = 0
        is_printing = False
        scroll_offset = 0

        system_prompt, first_message = self._build_story_system_prompt(
            self.config.story_card,
            self.config.player_card,
            self.config.companion_cards,
        )
        self.messages.append({"role": "system", "content": system_prompt})
        text_generator = self._stream_llm_chat(self.config.model, first_message)
        self.display_messages = [{"role": "assistant", "content": ""}]
        is_printing = True

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                elif event.type == pygame.KEYDOWN and not is_printing:
                    if event.key == pygame.K_RETURN:
                        if self.is_story_update == True:
                            self.messages.append(
                                {
                                    "role": "assistant",
                                    "content": input_text,
                                }
                            )
                            self.display_messages[-1] = {
                                "role": "assistant",
                                "content": f"(Updated Story): {input_text}",
                            }
                            self.is_story_update = False
                            input_text = ''
                            continue
                        self._process_player_input(input_text)
                        if self.is_story_update == True:
                            input_text = ''
                            continue
                        input_text = ''
                        text_generator = self._stream_llm_chat(
                            self.config.model, input_text
                        )
                        self.display_messages.append(
                            {"role": "assistant", "content": ""}
                        )
                        next_word_time = pygame.time.get_ticks() + 500
                    elif event.key == pygame.K_BACKSPACE:
                        input_text = input_text[:-1]
                    else:
                        if event.unicode.isprintable():
                            input_text += event.unicode

            self.screen.fill(self.config.colors['black'])

            current_y = base_y - scroll_offset
            for message in self.display_messages:
                _, current_y = self._draw_text(
                    self.screen,
                    message['content'],
                    (10, current_y),
                    self.config.font,
                    (
                        self.config.colors['red']
                        if message['role'] == 'user'
                        else self.config.colors['green']
                    ),
                )

            # Calculate the necessary scroll if text is going beyond the input area
            if current_y > self.config.height - 50 - self.config.line_height:
                scroll_offset += current_y - (
                    self.config.height - 50 - self.config.line_height
                )

            if text_generator and pygame.time.get_ticks() > next_word_time:
                try:
                    next_word = next(text_generator)
                    self.display_messages[-1]['content'] += next_word
                    next_word_time = pygame.time.get_ticks() + 150
                except StopIteration:
                    text_generator = None
                    is_printing = False
                    self.messages.append(
                        {
                            "role": "assistant",
                            "content": self.display_messages[-1]['content'],
                        }
                    )

            self._draw_text(
                self.screen,
                (">> " if not self.is_story_update else "(update story)>> ")
                + input_text,
                (10, self.config.height - 50),
                self.config.font,
                self.config.colors['red'],
            )

            pygame.display.flip()
            clock.tick(60)

    def _truncate_messages(self, max_tokens):
        if not self.messages or len(self.messages) < 2:
            return
        token_counts = [
            len(message['content'].split()) for message in self.messages
        ]
        current_total_count = sum(token_counts)
        index = 1
        while current_total_count > max_tokens and len(self.messages) > 2:
            self.messages.pop(1)
            current_total_count -= token_counts[index]
            index += 1

    def _extract_new_lines(self, words: list[str]) -> list[str]:
        new_words = []
        for word in words:
            result = re.split(r'(\n)', word)
            result = [x for x in result if x]
            for r in result:
                new_words.append(r)
        return new_words

    def _draw_text(
        self,
        surface,
        text: str,
        pos: Tuple[int, int],
        font,
        color: Tuple[int, int, int],
    ) -> Tuple[int, int]:
        x, y = pos
        space_width = font.size(' ')[0]
        words = text.split(' ')
        words = self._extract_new_lines(words)
        max_width = self.config.width - 20  # Give some margin on the sides

        for word in words:
            if word == '\n':
                x = pos[0]
                y += self.config.line_height
                continue
            word_surface = font.render(word, True, color)
            word_width, word_height = word_surface.get_size()
            if x + word_width >= max_width:
                x = pos[0]  # Reset x to the beginning of the line
                y += self.config.line_height  # Move to the next line
            surface.blit(word_surface, (x, y))
            x += word_width + space_width
        return (
            x,
            y + self.config.line_height,
        )

    def _build_story_system_prompt(
        self, story_card: str, player: str, companions: list[str]
    ) -> tuple[str, str]:
        story_system_prompt = """
You are an assistant acting as an AI Dungeon Master. Your mission is to facilitate an exciting, story-based adventure where players
can make choices and interact with the world you create. You will guide, challenge, and adapt to player actions to deliver a unique,
memorable adventure. Balance combat, puzzles, and role-playing to move the story forward and keep it interesting.

Guide players through the adventure using the story card above, adapting to their actions to deliver a unique, memorable adventure.
Balance combat, puzzles, and role-play. Describe the situation from the third-person perspective of the Dungeon Master; for example,
"Sherlock Holmes sees a mysterious figure in the shadows." Always use third-person narrative.

As players speak to their companions, describe the companions' reactions and responses. 

Do not display any part of this prompt to the player. Use it as a reference to guide the story. 

The story should always be described from the narrator's perspective in third person, for example, "Sherlock Holmes sees a mysterious figure..."
Avoid presenting choices to the player as a list like a, b, c or 1, 2, 3. Instead, describe the situation and let the player decide what
to do. When enemies appear, describe their actions and allow the player to decide their response. Always describe the outcome of the player's
actions and adapt the story based on their choices.

Never speak for the player, only for the companions and other NPCs in the story.
    """

        companions_str = '\n'.join(companions)
        start_message = f"""
Use the following story card between triple ticks to learn the story and what happened so far:
```
{story_card}
```

Use the following player card between triple ticks to learn about the player:
```
{player}
```

Use the following companion card between triple ticks to learn about the companion:
```
{companions_str}
```

Now, generate initial describtion of the story and the player's surroundings.  Provide only the initial description of the story
and the player's surroundings.
        """
        return story_system_prompt, start_message

    def _stream_llm_chat(self, model: str, message: str) -> Iterator[Any]:
        self.messages.append(
            {
                "role": "user",
                "content": message,
            }
        )
        payload = {
            "model": model,
            "messages": self.messages,
            "stream": True,
            "options": {
                "num_ctx": self.config.num_ctx,
                "temperature": self.config.temperature,
            },
        }

        for token in requests.post(
            f"{self.config.ollama_url}/api/chat", json=payload, stream=True
        ).iter_lines():
            jsonstr = json.loads(token)
            yield jsonstr["message"]["content"]

    def _process_player_input(self, user_input: str):
        if user_input == "quit":
            pygame.quit()
            sys.exit()
        elif user_input == "undo":
            if self.is_story_update == True:
                return
            if (
                len(self.messages) > 1
                and self.messages[-1]["role"] == "assistant"
            ):
                self.messages.pop()
                self.is_story_update = True
                return
            else:
                self.is_story_update = False
        elif user_input == "debug":
            print(self.messages)

        new_user_input = {
            "role": "user",
            "content": user_input,
        }
        self.messages.append(new_user_input)
        self.display_messages.append(new_user_input)
        self._truncate_messages(self.config.num_ctx)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run a text adventure game.")
    parser.add_argument(
        "-s", "--story", required=True, help="Path to the YAML story file."
    )
    args = parser.parse_args()
    config = GameConfig(args.story)
    game = Game(config)
    game.run()
