# Bar-Bot
Automatic Cocktail Maker (Work in Progress)

Project startet on 17th November 2024

This is my take on the Automatic Bartender Robot (original: https://github.com/sidlauskaslukas/barbot/tree/master?tab=readme-ov-file)

# Details
- You can freely decide which drink you want to put on which position. Then you can configure the drink and location in the webserver. (/config)
- You can easily create new recipes and manage your existing ones. (/rezepte)
- You can decide what drink is made with a click of a button. The available recipes are shown in green, while the other ones are red. You can see details on why a recipe is not available.
- Additionally you can see the contents of a recipe with the "?" icon
- Chancing location of drinks is as easy as it gets. Just set the name of your drink and the position.
- Adding new recipes is also very easy. Just select the drink and the quantity, and a file with the instructions for the esp is automatically created.
- When Bottles are reordered, it still works perfectly, as long as you define the new locations on the /config page

# Technical Details
The ESP has minimal code on it. It only takes 2 commands.
- move to position x and
- activate servo, hold for x ms, then go back
The Raspberry Pi takes the heavy lifting, by sending the right commands to the ESP

# Already done:
- All parts are assembled (except liquor holding and pouring construction)
- Project almost compleately digitalized for easyer testing, troubleshooting ect. (3D files, ESP32 emulators...)
- Raspberry Pi Server programmed and functional
- ESP32 Code functional and taking commands from the Raspberry Pi
- Basic Web-Interface for testing purposes.
- Software for the Raspberry Pi and ESP32
- Hardware testing
- Parameter tuning
- User Interface
- Fully functional Web interface to configure, edit, add, remove recipes and drinks with ther corresponding position
- (Done at 22th November 2024)

# Currently working on:
- Woodwork
- Final Adjustments

# Total Hardware cost (not including 3D printing material): to much

# Here are a few images
![As of 22th November 2024](https://github.com/leofleischmann/Bar-Bot/blob/aef47b5e8c036a115e24fcea56c180e6691d0192/Progress_report.jpeg?raw=true)
![As of 22th November 2024](https://github.com/leofleischmann/Bar-Bot/blob/81d38c1ef765c1620e4a5a3b449e7f446b287d88/AutoBarTender_constructed%20v13.png?raw=true)

# Installation on the Raspberry Pi
- Simply copy the Repo on your Raspberry Pi
- Make sure Port 5001 and 5002 are not in use
- Create a service that starts the server.py script automatically
- You can now find the webserver on port 5001.
- When no Wifi is enabled, a HotSpot is created named "barbot" with password "12345678". You can connect and then configure a new Wifi on Port 5002.
- Have Fun :)

# About the Website:
![index1.html](https://github.com/leofleischmann/Bar-Bot/blob/c0456712a47b8941aefea4feb90bd9ac971c621a/Images/index1.png?raw=true)
![index2.html](https://github.com/leofleischmann/Bar-Bot/blob/c0456712a47b8941aefea4feb90bd9ac971c621a/Images/index2.png?raw=true)
![index3.html](https://github.com/leofleischmann/Bar-Bot/blob/c0456712a47b8941aefea4feb90bd9ac971c621a/Images/index3.png?raw=true)
![index4.html](https://github.com/leofleischmann/Bar-Bot/blob/c0456712a47b8941aefea4feb90bd9ac971c621a/Images/index4.png?raw=true)
![index5.html](https://github.com/leofleischmann/Bar-Bot/blob/c0456712a47b8941aefea4feb90bd9ac971c621a/Images/index5.png?raw=true)
![config1.html](https://github.com/leofleischmann/Bar-Bot/blob/c0456712a47b8941aefea4feb90bd9ac971c621a/Images/config1.png?raw=true)
![calib1.html](https://github.com/leofleischmann/Bar-Bot/blob/c0456712a47b8941aefea4feb90bd9ac971c621a/Images/calib1.png?raw=true)
![rezepte1.html](https://github.com/leofleischmann/Bar-Bot/blob/c0456712a47b8941aefea4feb90bd9ac971c621a/Images/rezepte1.png?raw=true)
![rezepte2.html](https://github.com/leofleischmann/Bar-Bot/blob/c0456712a47b8941aefea4feb90bd9ac971c621a/Images/rezepte2.png?raw=true)
