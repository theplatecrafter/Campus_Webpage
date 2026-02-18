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
        
    #logs folder
    if not os.path.exists("features/logs"):
        os.mkdir("features/logs")

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
            f.write("[]")
    
    #permissions json
    if not os.path.exists("features/permissions.json"):
        with open("features/permissions.json", "w") as f:
            f.write("""{
    "DEV":0
}""")
            
    # moderation json
    if not os.path.exists("features/moderation.json"):
        with open("features/moderation.json", "w") as f:
            f.write("{}")
            
    # moderation log json
    if not os.path.exists("features/moderation_log.json"):
        with open("features/logs/moderation_log.json", "w") as f:
            f.write("{}")
    
    # server log json
    if not os.path.exists("features/server_log.json"):
        with open("features/logs/server_log.json", "w") as f:
            f.write("{}")
