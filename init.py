#creates blank features folder

def initialize():
    import os

    # ===================
    # FOLDERS
    # ===================


    # features folder
    if not os.path.exists("features"):
        os.mkdir("features")

    #chat folder
    if not os.path.exists("features/chat"):
        os.mkdir("features/chat")

    # ===================
    # FILES
    # ===================


    #users json
    if not os.path.exists("features/users.json"):
        with open("features/users.json", "w") as f:
            f.write("{}")



    #chat json
    if not os.path.exists("features/chat/chat.json"):
        with open("features/chat/chat.json", "w") as f:
            f.write("{}")