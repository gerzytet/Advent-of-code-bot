import asyncio

import discord
from discord.ext import commands
import shelve
import datetime
import urllib
import json
from collections import defaultdict
from threading import Lock

intents = discord.Intents.default()
intents.message_content = True
leaderboard_lock = Lock()

client = commands.Bot(command_prefix='/', intents=intents)

REGISTRATION_CHANNEL_ID = 1047599570877698048
MESSAGE_CHANNEL_ID = REGISTRATION_CHANNEL_ID
leaderboard_url = r'https://adventofcode.com/2022/leaderboard/private/view/432147.json'
with open('cookie.txt') as cookie_file:
    cookie = cookie_file.read()
header = {
    'cookie': cookie
}

new_solves = defaultdict(lambda: defaultdict(dict))

def get_data():
    request = urllib.request.Request(leaderboard_url, headers=header)
    with urllib.request.urlopen(request) as url:
        data = json.loads(url.read().decode())
        return data

def initial_data():
    with shelve.open('leaderboard') as db:
        db['last_refresh'] = datetime.datetime.now()
        db['data'] = get_data()

def refresh_leaderboard(refresh_time):
    try:
        leaderboard_lock.acquire()
        with shelve.open('leaderboard') as db:
            if 'last_refresh' in db and datetime.datetime.now() - db['last_refresh'] < refresh_time:
                print('Skipping refresh')
                return
            print('Refreshing leaderboard')
            db['last_refresh'] = datetime.datetime.now()
            new_data = get_data()
            old_data = db['data'] if 'data' in db else {}

            if 'members' not in old_data:
                old_data['members'] = {}
            new_members = new_data['members']
            old_members = old_data['members']

            for new_member in new_members.keys():
                solves = new_members[new_member]['completion_day_level']
                for day in solves.keys():
                    stars = solves[day].keys()
                    for star in stars:
                        if new_member not in old_members or day not in old_members[new_member]['completion_day_level'] or star not in old_members[new_member]['completion_day_level'][day]:
                            new_solves[new_member][day][star] = solves[day][star]['get_star_ts']

            db['data'] = new_data
    finally:
        leaderboard_lock.release()

def get_ordinal(number):
    lastdigit = int(str(number)[len(str(number)) - 1])
    last2 = int(str(number)[len(str(number)) - 2:])
    if last2 > 10 and last2 < 13:
        return str(number) + "th"
    if lastdigit == 1:
        return str(number) + "st"
    if lastdigit == 2:
        return str(number) + "nd"
    if lastdigit == 3:
        return str(number) + "rd"
    return str(number) + "th"

def star_count(aoc_user):
    with shelve.open('leaderboard') as leaderboard:
        members = leaderboard['data']['members']
        count = 0
        for day in members[aoc_user]['completion_day_level'].keys():
            count += len(members[aoc_user]['completion_day_level'][day].keys())
        return count

async def announce_new_solves():
    channel = client.get_channel(MESSAGE_CHANNEL_ID)
    print(new_solves)
    with shelve.open('users') as user_db:
        for member in new_solves.keys():
            for day in new_solves[member].keys():
                for star in new_solves[member][day].keys():
                    await channel.send(f'{(await channel.guild.fetch_member(user_db[member])).name} is the {get_ordinal(num_solvers(day, star))} one to solve day {day} star {star}.')
    new_solves.clear()

async def leaderboard_update_loop():
    while True:
        minutes = 20
        refresh_leaderboard(datetime.timedelta(minutes=minutes))
        #await announce_new_solves()
        await asyncio.sleep(minutes * 60)

@client.hybrid_command(name='register')
async def register(ctx, aoc_id):
    if ctx.channel.id == REGISTRATION_CHANNEL_ID:
        try:
            refresh_leaderboard(datetime.timedelta(minutes=0))
            leaderboard_lock.acquire()
            with shelve.open('leaderboard') as db:
                data = db['data']
                if str(aoc_id) in data['members']:
                    with shelve.open('users') as user_db:
                        if str(aoc_id) in user_db.keys() or str(ctx.author.id) in user_db.values():
                            await ctx.send('You are already registered!')
                        else:
                            user_db[aoc_id] = str(ctx.author.id)
                            await ctx.send('Registered!')
                else:
                    await ctx.send('Invalid ID. Please make sure you are registered on the private leaderboard.')
            leaderboard_lock.release()

        except ValueError:
            await ctx.send('Invalid ID')
            return

@client.hybrid_command(name='leaderboard')
async def leaderboard(ctx):
    if ctx.channel.id == REGISTRATION_CHANNEL_ID:
        refresh_leaderboard(datetime.timedelta(minutes=2))
        leaderboard_lock.acquire()
        with shelve.open('leaderboard') as db:
            with shelve.open('users') as user_db:
                leaderboard = []
                for user in user_db.keys():
                    leaderboard.append(((await ctx.channel.guild.fetch_member(user_db[user])).name, star_count(user)))
                leaderboard.sort(key=lambda x: x[1], reverse=True)
                leaderboard = leaderboard[:10]
                out = ''
                for i in range(len(leaderboard)):
                    out += f'> {i + 1}. {leaderboard[i][0]} - {leaderboard[i][1]} stars\n'
                await ctx.send(out)
        leaderboard_lock.release()

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    asyncio.create_task(leaderboard_update_loop())

with open('token.txt', 'r') as f:
    token = f.read()

client.run(token)
