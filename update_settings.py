import json

settings_path = "C:/Users/HOME/AppData/Roaming/DeeMusic/settings.json"

with open(settings_path, 'r') as f:
    settings = json.load(f)

settings['lyrics']['embed_sync_lyrics'] = True

with open(settings_path, 'w') as f:
    json.dump(settings, f, indent=4)

print("Updated embed_sync_lyrics to True") 