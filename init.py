#creates blank features folder
import os

# features folder
if not os.path.exists("features"):
    os.mkdir("features")

#users json
if not os.path.exists("features/chat/chat.json"):
    with open("features/chat/chat.json", "w") as f:
        f.write("{}")

#chat folder
if not os.path.exists("features/chat"):
    os.mkdir("features/chat")

#chat json
if not os.path.exists("features/chat/chat.json"):
    with open("features/chat/chat.json", "w") as f:
        f.write("{}")