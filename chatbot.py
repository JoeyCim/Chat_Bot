#!/usr/bin/env python3

import binascii
import random
import re
import socket
import time
import xml.etree.ElementTree as ET
from collections import OrderedDict
import requests

FOUL_WORDS = ["smeckledorfed"]
BALL_RESPONSES = ["It will happen!", "The odds are in your favor.",  
        "You might get lucky!", "Maybe on a blue moon.",
        "The odds are stacked against you.", "Not today I'm afraid."]

class Bot(object):
    def __init__(self, reg_name, reg_id, password, disp_name, avatar, room_id):
        self.reg_name = reg_name
        self.reg_id = reg_id
        self.password = encode(password.encode("utf-8"))
        self.disp_name = disp_name
        self.avatar = avatar
        self.room_id = room_id
        self.users = UserList()
        self.address = get_address()
        self.connect_socket()

    def connect_socket(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect(self.address)
    
    def get_login_data(self):
        """Log the bot in to receive some parameters needed for connecting to 
        its room."""

        # Let 'em know we're here.
        y_str = format_XML("y",{"r":"8","v":"0","u":str(self.reg_id)})
        self.sock.send(y_str)
        self.recv_XML()

        # Send in account details to receive login data.
        v_str = format_XML("v",{"n":self.reg_name,"p":self.password})
        self.sock.send(v_str)
        login_packet = self.recv_XML()
        login_data = ET.fromstring(login_packet).attrib
        self.sock.close()
        return login_data

    def get_room_data(self):
        self.connect_socket()

        # Let the room know we're coming to retrieve some necessary info.
        y_str = format_XML("y", {"r":str(self.room_id),"m":"1", "v":"0", 
            "u":str(self.reg_id)})
        self.sock.send(y_str)
        room_packet = self.recv_XML()
        room_data = ET.fromstring(room_packet).attrib
        print(room_data)
        return room_data

    def get_j2(self, login_data, room_data):
        """Make the formidable j2 packet, which is used to actually connect
        the bot to its chat once we have gone through the other motions.
        """
        
        # The order of attributes in the XML string is sensitive, so an 
        # OrderedDict is used to preserve the order in which keys are added.
        j2_attr = OrderedDict()
        j2_attr["cb"] = int(time.time())
        j2_attr["l5"] = "65535"
        j2_attr["l4"] = "123"
        j2_attr["l3"] = "456"
        j2_attr["l2"] = "0"
        j2_attr["q"] = "1"
        j2_attr["y"] = room_data["i"]
        j2_attr["k"] = login_data["k1"]
        j2_attr["k3"] = login_data["k3"]
        
        if "d1" in login_data:
            j2_attr["d1"] = login_data["d1"]
        
        j2_attr["z"] = "12"
        j2_attr["p"] = "0"
        j2_attr["c"] = self.room_id
        j2_attr["r"] = ""
        j2_attr["f"] = "0"
        j2_attr["e"] = ""
        j2_attr["u"] = login_data["i"]
        
        if "d0" in login_data:
            j2_attr["d0"] = login_data["d0"]

        for i in range(2,16):
            di = "d" + str(i)
            if (di) in login_data:
                j2_attr[di] = login_data[di]

        if "dx" in login_data:
            j2_attr["dx"] = login_data["dx"]

        if "dt" in login_data:
            j2_attr["dt"] = login_data["dt"]

        j2_attr["N"] = self.reg_name
        j2_attr["n"] = self.disp_name
        j2_attr["a"] = self.avatar
        j2_attr["h"] = "google.com"
        j2_attr["v"] = "3"

        j2 = format_XML("j2", j2_attr)
        return j2 

    def connect(self):
        login_data = self.get_login_data()
        room_data = self.get_room_data()
 
        try:
            j2 = self.get_j2(login_data, room_data)
        except KeyError as e:
            print("Error: unable to log in, please check your bot's " \
                    "provided regname and password.")
            return
       
        print(j2)
        self.sock.send(j2)
        login_response = self.recv_XML()
        
        if "Failed" in login_response:
            print("Errror: unable to access the chat, please check the " \
                    "provided chat ID and make sure the BOT power has " \
                    "been assigned. If those are both correct, then " \
                    "the j2 attributes might be outdated.")
            return
        
        print("Successfully connected to the chat.")

        # We are going to be blasted with some data  at first containing
        # information about who is logged into the chat and what messages
        # are in the chat's active history, but we are only going to pay
        # attention to the former. You might change this for real chat use,
        # but for simple testing that involves disconnecting/reconnecting
        # a bot frequently, this can cause some messages to be processed
        # multiple times, which is a bit of a pain.
        self.get_init_users()   
        self.listen()
    
    def listen(self):
        while True:
            data = self.recv_XML()
            tag = data[1:data.find(" ")]
            if tag == "u": #User joined
                user_data = ET.fromstring(data).attrib
                
                # Sometimes users re-login without properly logging out (e.g.
                # when their rank is changed), so we don't want to have any
                # duplicates.
                self.users.remove(user_data["u"])
                self.users.append(user_data)
                print(self.users)
            if tag == "l": #User left
                user_id = ET.fromstring(data).attrib["u"]
                self.users.remove(id)
                print(self.users)
            if tag == "m": #User spoke
                content = ET.fromstring(data).attrib
                user_id = content["u"]
                user_message = content["t"]
         
                if is_foul(user_message):
                    self.kick(user_id, "Offensive language")
                elif user_message[0] == "!":
                    self.parse_command(user_message, user_id)
            if tag == "logout":
                return
    
    def parse_command(self, command, user_id):
        if command.startswith("!roll"):
            match = re.match(r"^!roll (\d+)[dD](\d+)\s*$", command)
            if match:
                num_dice = int(match.group(1))
                dice_size = int(match.group(2))
                if (num_dice < 1 or num_dice > 10 or dice_size < 1
                        or dice_size > 100):
                    self.pc(user_id, "Invalid syntax: use !roll [1-10]D[1-100]")
                else:
                    result = ""
                    while num_dice > 0:
                        result += str(random.randint(1,dice_size)) + " "
                        num_dice -= 1
                    self.say(result)
            else:
                self.pm(user_id, "Invalid syntax: use !roll [1-10]D[1-100]")
        
        if command.startswith("!8ball "):
            result = "8ball: " + random.choice(BALL_RESPONSES)
            self.say(result)
        
        if command.startswith("!drlove"): 
            names = command.split()
            if len(names) == 3:
                hashval = binascii.crc32((names[1] + names[2]).encode("utf-8"))
                love = str((hashval % 100) + 1) + "%"
                self.say("Dr. Love thinks there is a %s love connection " \
                        "between %s and %s." % (love, names[1], names[2]))
            else:
                self.pm(user_id, "Invalid syntax: use !drlove NAME1 NAME2")

    def say(self, message):
        """Say something to the chat."""
        message_data = format_XML("m", {"t":message,"u":self.reg_id})
        self.sock.send(message_data)

    def kick(self, user_id, reason):
        """Kick a user."""
        kick_data = format_XML_ord("c", ("p",reason), ("u",user_id), ("t","/k"))
        self.sock.send(kick_data)

    def pm(self, user_id, message):
        """Send a private message to a user."""
        pm_data = format_XML_ord("p",("u",user_id), ("t",message))
        self.sock.send(pm_data)

    def pc(self, user_id, message):
        """Initiate a private chat with a user."""
        pc_data = format_XML_ord("p", ("u",user_id),("t",message),
                ("s",2), ("d",self.reg_id))
        self.sock.send(pc_data)
    
    def get_init_users(self):
        """Assemble a list of users from the initial chunk of data sent to the 
        bot. The end of this 'initial data stream' is marked by '<done />'.
        """
        while True:
            data = self.recv_XML()
            tag = data[1:data.find(" ")]
            if tag == "u":
                user_data = ET.fromstring(data).attrib
                self.users.append(user_data)
            if tag == "done":
                return

    def recv_XML(self):
        """Fetch one chunk of XML data (a single element) from the socket
        stream and decode it. Multi-byte characters are permitted.
        """
        tag = b""
        next_ch = self.sock.recv(1)
        
        while next_ch != b'\0':
            tag += next_ch
            next_ch = self.sock.recv(1)
        return tag.decode("utf-8")
    

class UserList(list):
    """An extension of list that stores dictionaries of user data. Used to
    make a few common operations a little bit cleaner.
    """
    def remove(self,user_id):
        for user in self:
            if user["u"] == user_id:
                super().remove(user)

    def get(self,user_id):
        for user in self:
            if user["u"] == user_id:
                return user
        return None

def get_address():
    """Pull an address from a page containing address info in JSON."""
    json_data = requests.get("http://xat.com/web_gear/chat/ip2.htm").json()
    ip_groups = json_data['F0'][1:]
    ip_group = ip_groups[0]
    ip = ip_group[0]
    port = 10000
    return (ip, port)

#TODO: Refactor to consolidate the below two functions
def format_XML(tag, attributes):
    """Return the corresponding (UTF-8 encoded) XML string from a given tag         and a dictionary of attributes.
    """
    XML_string = "<%s " % (tag)
    for key in attributes:
        XML_string += '%s="%s" ' % (key,attributes[key])
    XML_string += '/>\0'
    return XML_string.encode("utf-8")

def format_XML_ord(tag, *args):
    """Return the corresponding (UTF-8 encoded) XML string from a given tag         and an arbitrary number of tuples, each representing an attribute, with the     order that the tuples are passed matching the order that they appear in the
    XML string.
    """
    XML_string = "<%s " % (tag)
    for tup in args:
        XML_string += '%s="%s" ' % (tup[0],tup[1])
    XML_string += '/>\0'
    return XML_string.encode("utf-8")

def is_foul(content):
    """Check whether some content contains offensive language."""
    for word in FOUL_WORDS:
        if word in content:
            return True
    return False

def encode(password):
    """Return a 32-bit 2's complement representation of a crc32 checksum with
    a preceding '$'. This is how account passwords are encrypted."""
    encrypted = binascii.crc32(password)
    
    # We need the 32 bit binary number 'encoded' to be interpreted as a 32
    # bit 2's complement number.
    encrypted_2sc = -(encrypted >> 31)*(2**31) + (encrypted & 0x7FFFFFFF)
    return "$"+str(encrypted_2sc)

if __name__ == "__main__":
    reg_name = ""
    reg_id = 0 
    password = ""
    disp_name = ""
    avatar = 0
    room_id = 0
    bot = Bot(reg_name, reg_id, password, disp_name, avatar, room_id)
    bot.connect()
