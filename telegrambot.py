import telebot
import ncellapp
from os import path
from aiohttp import web
import ast, inspect, logging
import json, base64, time, ssl

import models

#!? Finding the absolute path of the config file
scriptPath = path.abspath(__file__)
dirPath = path.dirname(scriptPath)
configPath = path.join(dirPath,'config.json')

config = json.load(open(configPath))

logging.basicConfig(filename=config['telegram']['errorLog'],
        filemode='a',
        format='🔴 %(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
        datefmt='%H:%M:%S',
        level=logging.ERROR)

logger = logging.getLogger('catch_all')
loggerConsole = logging.Logger('catch_all')

dbSql = models.dbQuery(config['database'])
language = json.load(open(config['language']))

bot = telebot.TeleBot(config['telegram']['botToken'], parse_mode='HTML')

#! Configuration for webhook
webhookBaseUrl = f"https://{config['telegram']['webhookOptions']['webhookHost']}:{config['telegram']['webhookOptions']['webhookPort']}"
webhookUrlPath = f"/{config['telegram']['botToken']}/"

app = web.Application()

#: Process webhook calls
async def handle(request):
    if request.match_info.get('token') == bot.token:
        request_body_dict = await request.json()
        update = telebot.types.Update.de_json(request_body_dict)
        bot.process_new_updates([update])
        return web.Response()
    else:
        return web.Response(status=403)

app.router.add_post('/{token}/', handle)

#: Check if the user is subscribed or not, returns True if subscribed
def isSubscribed(message, sendMessage=True):
    callerFunction = inspect.stack()[1][3]
    telegramId = message.from_user.id
    subscribed = True
    try:
        status = bot.get_chat_member(config['telegram']['channelId'], telegramId)
        
        if status.status == 'left':
            subscribed = False
        else:
            return True

    except Exception:
        subscribed = False

    if not subscribed:
        #!? Send the links if sendMessage is True
        if sendMessage:
            bot.send_message(message.from_user.id, text=language['notSubscribed']['en'].format(message.from_user.first_name), reply_markup=telebot.types.InlineKeyboardMarkup([
            [telebot.types.InlineKeyboardButton(text='Join Channel', url='https://t.me/H9YouTube'),
            telebot.types.InlineKeyboardButton(text='Subscribe Channel', url='https://www.youtube.com/h9youtube?sub_confirmation=1')],
            [telebot.types.InlineKeyboardButton('❤️ Done', callback_data=f'cb_isSubscribed:{callerFunction}')]
            ]))

        return False

#: Reply keyboard for cancelling a process
def cancelReplyKeyboard():
    cancelKeyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    cancelButton = telebot.types.KeyboardButton(text='❌ Cancel')
    cancelKeyboard.add(cancelButton)

    return cancelKeyboard

#: Main reply keyboard
def mainReplyKeyboard(message):
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    button1 = telebot.types.KeyboardButton(text='👥 Accounts')
    button2 = telebot.types.KeyboardButton(text='➕ Register')
    button3 = telebot.types.KeyboardButton(text='🔐 Encryption')
    button4 = telebot.types.KeyboardButton(text='💰 Balance')
    button5 = telebot.types.KeyboardButton(text='💳 Recharge')
    button6 = telebot.types.KeyboardButton(text='💬 SMS')
    button7 = telebot.types.KeyboardButton(text='📦 Plans')
    button8 = telebot.types.KeyboardButton(text='📊 History')
    button9 = telebot.types.KeyboardButton(text='🔃 Switch')
    button10 = telebot.types.KeyboardButton(text='⚙️ Settings')
    button11 = telebot.types.KeyboardButton(text='⁉️ Help')
    button12 = telebot.types.KeyboardButton(text='🎁 Support Us')
    button13 = telebot.types.KeyboardButton(text='🏳️‍🌈 Others')

    userId = dbSql.getUserId(message.from_user.id)
    account = dbSql.getAccounts(userId)

    #! Reply keyboard for the users with accounts
    if account:
        if len(account) > 1:
            #!? More than one accounts
            keyboard.row(button9, button1)
            keyboard.row(button4, button5, button6)
            keyboard.row(button6, button7, button13)
            keyboard.row(button10, button11, button12)  
        else:
            #!? Only one account
            keyboard.row(button4, button5, button1)
            keyboard.row(button6, button7, button8)
            keyboard.row(button10, button11, button12)

    #! Reply keyboard for the users without any account
    else:
        keyboard.row(button2)
        keyboard.row(button10, button3)
        keyboard.row(button11, button12)

    return keyboard

#: Cancel handler
def cancelKeyboardHandler(message):
    userId = dbSql.getUserId(message.from_user.id)
    bot.send_message(message.from_user.id, '❌ Cancelled', reply_markup=mainReplyKeyboard(message))

#: Invalid refresh token handler for callbacks
def invalidRefreshTokenHandler_cb(call, userId, responseCode):
    accountId = dbSql.getSetting(userId, 'defaultAcId')
    dbSql.deleteAccount(userId, accountId)
    bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.id)
    bot.send_message(call.message.chat.id, language['newLoginFound']['en'] if responseCode=='LGN2003' else language['sessionExpired']['en'], reply_markup=mainReplyKeyboard(call))

#: Invalid refresh token handler for messages
def invalidRefreshTokenHandler(message, userId, responseCode):
    accountId = dbSql.getSetting(userId, 'defaultAcId')
    dbSql.deleteAccount(userId, accountId)
    bot.send_message(message.from_user.id, language['newLoginFound']['en'] if responseCode=='LGN2003' else language['sessionExpired']['en'], reply_markup=mainReplyKeyboard(message))
            
#: Unknown error handler for callbacks
def UnknownErrorHandler_cb(call, description, statusCode):
    bot.answer_callback_query(call.id, text=language['unknwonError']['en'].format(description, statusCode), show_alert=True)

#: Unknown error handler for messages
def unknownErrorHandler(message, description, errorCode):
    bot.send_message(message.from_user.id, text=language['unknwonError']['en'].format(description, statusCode), reply_markup=mainReplyKeyboard(message))

#: Updating the token in database after refreshing
def autoRefreshToken(userId, token): 
    dbSql.updateAccount(userId,dbSql.getSetting(userId, 'defaultAcId'), token)
   
@bot.message_handler(commands=['start'])
def start(message):
    telegramId = message.from_user.id
    userId = dbSql.getUserId(telegramId)
    if userId:
        #!? If user is already in the database
        bot.send_message(message.from_user.id, text=language['greet']['en'].format(message.from_user.first_name), reply_markup=mainReplyKeyboard(message))
    else:
        #!? If not, add the user in the database
        #dbSql.setUserId(telegramId)
        bot.send_message(message.from_user.id, text=language['greetFirstTime']['en'].format(message.from_user.first_name),disable_web_page_preview=True, reply_markup=mainReplyKeyboard(message))

#! Ping pong
@bot.message_handler(commands=['ping'])
def ping(message):
    bot.send_message(message.from_user.id, text=language['ping']['en'], reply_markup=mainReplyKeyboard(message))

@bot.message_handler(commands=['register'])
def register(message):
    if isSubscribed(message):
        sent = bot.send_message(message.from_user.id, text=language['enterNumber']['en'], reply_markup=cancelReplyKeyboard())
        bot.register_next_step_handler(sent, getOtp)

def getOtp(message, called=False):
    #!? Check for cancel only if not called because call don't have 'text' attribute
    if not called and message.text == '❌ Cancel':
        cancelKeyboardHandler(message)
    else:
        userId = dbSql.getUserId(message.from_user.id)
        #!? MSISDN is previous text if not called, else it must be on the database
        msisdn = message.text if not called else dbSql.getTempdata(userId, 'registerMsisdn')
           
        ac = ncellapp.register(msisdn)
        response = ac.sendOtp()

        #! OTP sent successfully
        if response.responseDescCode == 'OTP1000':
            sent = bot.send_message(message.from_user.id, language['enterOtp']['en'], reply_markup=genMarkup_invalidOtp(reEnter=False))
            if not called:
                #!? Add the msisdn in the database if not called
                dbSql.setTempdata(dbSql.getUserId(message.from_user.id), 'registerMsisdn', message.text)     
            
            bot.register_next_step_handler(sent, getToken)
       
        #! OTP generation exceed
        elif response.responseDescCode == 'OTP2005':
            #!? Remove the MSISDN from temp database
            dbSql.setTempdata(userId, 'registerMsisdn', None)
            if called:
                sent = bot.edit_message_text(chat_id=message.message.chat.id, message_id=message.message.id, text=language['otpSendExceed']['en'], reply_markup=cancelReplyKeyboard())
            else:
                sent = bot.send_message(message.from_user.id, language['otpSendExceed']['en'], reply_markup=cancelReplyKeyboard())
                bot.register_next_step_handler(sent, getOtp)
        
        #! Invalid Number
        elif response.responseDescCode == 'LGN2007':
            sent = bot.send_message(message.from_user.id, language['invalidNumber']['en'])
            bot.register_next_step_handler(sent, getOtp)
        
        else:
            UnknownErrorHandler(message, response.responseDesc, response.statusCode)

def getToken(message):
    if message.text == '❌ Cancel':
        cancelKeyboardHandler(message)
    else:
        userId = dbSql.getUserId(message.from_user.id)
        msisdn = dbSql.getTempdata(userId, 'registerMsisdn')
        ac = ncellapp.register(msisdn)
        response = ac.getToken(message.text)
        
        #! Successfully registered
        if response.responseDescCode == 'OTP1000':
            dbSql.setAccount(userId, ac.token, models.genHash(msisdn))
            
            #!? Remove the register msisdn from the database
            dbSql.setTempdata(userId,'registerMsisdn', None)
            
            bot.send_message(message.from_user.id, language['registeredSuccessfully']['en'].format(msisdn), reply_markup=mainReplyKeyboard(message))
        
        #! OTP attempts exceed
        elif response.responseDescCode == 'OTP2002':
            bot.send_message(message.from_user.id, language['otpAttemptExceed']['en'], reply_markup=genMarkup_invalidOtp(reEnter=False))
        
        #! Invalid OTP
        elif response.responseDescCode == 'OTP2003':
            bot.send_message(message.from_user.id, language['invalidOtp']['en'], reply_markup=genMarkup_invalidOtp())
        
        #! OTP Expired
        elif response.responseDescCode == 'OTP2006':
            bot.send_message(message.from_user.id, language['otpExpired']['en'], reply_markup=genMarkup_invalidOtp())

        #! Unknown error
        else:
            UnknownErrorHandler(message, response.responseDesc, response.statusCode)

#: Keyboard markup for unsuccessful registration
def genMarkup_invalidOtp(reEnter=True):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.one_time_keyboard=True
    markup.row_width = 2
    
    #!? Add button to re-enter the otp if reEnter is True
    if reEnter:
        markup.row(telebot.types.InlineKeyboardButton('Re-Enter OTP', callback_data='cb_reEnterOtp'))
    
    markup.add(telebot.types.InlineKeyboardButton('Re-send OTP', callback_data='cb_reSendOtp'),
        telebot.types.InlineKeyboardButton('Change Number', callback_data='cb_changeRegisterNumber'))

    return markup

#: Manage accounts
@bot.message_handler(commands=['accounts'])
def accounts(message):
    markup = genMarkup_accounts(message, action='select')
    bot.send_message(message.from_user.id, text= language['accounts']['en'] if markup else language['noAccounts']['en'], reply_markup=markup)

#: Markup for accounts, return None if accounts is None
def genMarkup_accounts(message, action):
    userId = dbSql.getUserId(message.from_user.id)
    accounts = dbSql.getAccounts(userId)
    defaultAcId = dbSql.getSetting(userId, 'defaultAcId')

    if accounts:
        buttons = []
        for i in range(len(accounts)):
            msisdn = ast.literal_eval(base64.b64decode(accounts[i][1]).decode())['msisdn']
            accountId = accounts[i][0]
            
            #!? Emoji for logged in account
            if str(accountId) == str(defaultAcId):
                buttons.append(telebot.types.InlineKeyboardButton(f'✅ {msisdn}', callback_data=f'cb_{action}Account_{msisdn}:{accountId}'))
            else:
                buttons.append(telebot.types.InlineKeyboardButton(msisdn, callback_data=f'cb_{action}Account_{msisdn}:{accountId}'))

        markup = telebot.types.InlineKeyboardMarkup()
        markup.one_time_keyboard=True
        markup.row_width = 2
        buttons.append(telebot.types.InlineKeyboardButton('➕ Add', callback_data='cb_registerNumber'))
        markup.add(*buttons)

        #!? Emoji for actions
        removeText = 'Remove✨' if action=='remove' else 'Remove'
        selectText = 'Login As✨' if action=='select' else 'Login As'

        markup.add(telebot.types.InlineKeyboardButton(selectText, callback_data='cb_selectAccount'), telebot.types.InlineKeyboardButton(removeText ,callback_data='cb_removeAccount'))    
        markup.add(telebot.types.InlineKeyboardButton('❌ Cancel', callback_data='cb_cancel'))
        
        return markup
    else:
        return None

#: Instantly login as another account
@bot.message_handler(commands=['switch'])
def switch(message):
    userId = dbSql.getUserId(message.from_user.id)
    accounts = dbSql.getAccounts(userId)
    if accounts:
        defaultAcID = dbSql.getSetting(userId, 'defaultAcId')

        #!? Get the index of current default account
        for i,j in enumerate(accounts):
            if j[0] == defaultAcID:
                defaultAcIndex = i
        
        #!? If (condition), more accounts should be there ahead of that index
        ## Make defaultAcIndex+1 as the default account
        if len(accounts) > defaultAcIndex+1:
            accountId = accounts[defaultAcIndex+1][0]
            dbSql.setSetting(userId, 'defaultAcId', accountId)

        #!? If no accounts ahead, make the first account as the default account
        else:
            accountId = accounts[0][0]
            dbSql.setSetting(userId, 'defaultAcId', accountId)

        bot.send_message(message.chat.id, f"{language['loggedinAs']['en'].format(accountId)}")
    else:
        register(message)

#: Balance check  
@bot.message_handler(commands=['balance'])
def balance(message, called=False):
    if called or isSubscribed(message):
        userId = dbSql.getUserId(message.from_user.id)
        account = dbSql.getDefaultAc(userId)
        
        if account:
            acc = ncellapp.ncell(token=account[1], autoRefresh=True, afterRefresh=[__name__, 'autoRefreshToken'], args=[userId, '__token__']) 
            response = acc.viewBalance()
            
            #! Success
            if response.responseDescCode == 'BAL1000':
                balanceFormat(message, response.content['queryBalanceResponse'], called)
            
            #! Invalid refresh token
            elif response.responseDescCode in ['LGN2003', 'LGN2004']:
                invalidRefreshTokenHandler(message, userId, response.responseDescCode)
            
            #! Unknown error
            else:
                unknownErrorHandler(message, response.responseDesc, response.statusCode)
        else:
            register(message)

#: Balance parser
def balanceFormat(message, response, called):
    text = f"💰 Credit Balance\n\nBalance Rs. {response['creditBalanceDetail']['balance']}\nRecharged On: {response['creditBalanceDetail']['lastRechargeDate']}"

    #! If SMS balance
    if response['smsBalanceList']:
        text += '\n\n💬 SMS Balance\n'
        #? I don't know the response structure, LOL
        text += str(response['smsBalanceList'])

    #! If data balance
    if response['dataBalanceList']:
        text += '\n\n🌐 Data Balance\n'
        #? I don't know the response structure, LOL
        text += str(response['dataBalanceList'])

    #! If voice balance
    if response['voiceBalanceList']:
        text += '\n\n🎤 Voice Balance\n'
        #? Not sure the structure may change for different items
        try:
            for i in response['voiceBalanceList']:
                text+= f"\n✨{i['ncellName'].capitalize()} {i['freeTalkTime']} {i['talkTimeUom'].lower()}\nExpires on: {i['expDate']}"
        except Exception:
            text += str(response['voiceBalanceList']) 

    #! If unpaid loans
    if response['creditBalanceDetail']['loanAmount'] > 0:
        text += f"\n\n💸 Loan\n\nLoan amount Rs. {response['creditBalanceDetail']['loanAmount']}\nLoan taken on: {response['creditBalanceDetail']['lastLoanTakenDate']}"
        
        if called:
            bot.edit_message_text(chat_id=message.message.chat.id, message_id=message.message.id, text=text)
        else:
            bot.send_message(message.from_user.id, text)
    
    #! If no unpaid loans
    else:
        markup = None
        #! If the balance is less than 5, send take loan button
        if response['creditBalanceDetail']['balance'] <= 5:
            markup = telebot.types.InlineKeyboardMarkup()
            markup.one_time_keyboard=True
   
            markup.add(telebot.types.InlineKeyboardButton('🙏 Take Loan', callback_data='cb_confirmLoan'))
            
        if called:
            bot.edit_message_text(chat_id=message.message.chat.id, message_id=message.message.id, text=text, reply_markup=markup)
        else:
            bot.send_message(message.from_user.id, text, reply_markup=markup)

#: Loan
@bot.message_handler(commands=['loan'])
def loan(message, called=False):
    if called or isSubscribed(message):
        userId = dbSql.getUserId(message.from_user.id)
        account = dbSql.getDefaultAc(userId)

        if account:
            markup = telebot.types.InlineKeyboardMarkup()
            markup.one_time_keyboard=True
        
            markup.add(telebot.types.InlineKeyboardButton('❌ Cancel', callback_data='cb_cancel'), telebot.types.InlineKeyboardButton('🤝  Confirm loan', callback_data='cb_takeLoan'))

            if called:
                markup.add(telebot.types.InlineKeyboardButton('⬅️ Back', callback_data='cb_backToBalance'))
                bot.edit_message_text(chat_id=message.message.chat.id, message_id=message.message.id, text=language['confirmLoan']['en'], reply_markup=markup)
            else:     
                bot.send_message(message.from_user.id, language['confirmLoan']['en'], reply_markup=markup)
        else:
            if called:
                bot.delete_message(chat_id=message.message.chat.id, message_id=message.message.id)
            register(message)

 #: Customer profile       
@bot.message_handler(commands=['profile'])
def profile(message):
    if isSubscribed(message):
        userId = dbSql.getUserId(message.from_user.id)
        account = dbSql.getDefaultAc(userId)

        if account:
            acc = ncellapp.ncell(token=account[1], autoRefresh=True, afterRefresh=[__name__, 'autoRefreshToken'], args=[userId, '__token__'])
            response = acc.viewProfile()
            
            #! Success
            if response.responseDescCode == 'SUB1000':
                profileFormat(message, response.content['querySubscriberProfileResponse'])
            
            #! Invalid refresh token
            elif response.responseDescCode in ['LGN2003', 'LGN2004']:
                invalidRefreshTokenHandler(message, userId, response.responseDescCode)  
            
            #! Error
            else:
                UnknownErrorHandler(message, response.responseDesc, response.statusCode)
        else:
            register(message)

def profileFormat(message, response):
    if isSubscribed(message):
        text = f"{'👦🏻' if response['subscriberDetail']['gender'] == 'M' else '👧🏻'} Customer Profile\n\n"
        text += f"Name: {response['subscriberDetail']['firstName']} {response['subscriberDetail']['lastName']}\n"
        text += f"Phone number: {response['subscriberDetail']['msisdn']}\n"
        
        if response['subscriberDetail']['email'] != 'updateemail@ncell.com':
            text += f"Email: {response['subscriberDetail']['email']}\n"
        
        text += f"Registered on: {response['subscriberDetail']['registrationPeriod']}\n"
        
        if response['subscriberDetail']['profileImage']:
            text += f"<a href='{response['subscriberDetail']['profileImage']}'>Profile Picture🔻</a>"

        bot.send_message(message.from_user.id, text)

#: Plans and products
@bot.message_handler(commands=['plans'])
def plans(message):
    if isSubscribed(message):
        markup = genMarkup_plans(message)

        if markup:
            bot.send_message(message.from_user.id, text=language['selectPlanType']['en'], reply_markup=markup)
        else:
            register(message)

#: Markup for plans catagory
def genMarkup_plans(message):
    userId = dbSql.getUserId(message.from_user.id)
    account = dbSql.getDefaultAc(userId)
    
    if account:
        markup = telebot.types.InlineKeyboardMarkup()
        markup.one_time_keyboard=True
        markup.row_width = 2

        markup.add(telebot.types.InlineKeyboardButton('Subscribed Plans', callback_data='cb_subscribedPlans'), telebot.types.InlineKeyboardButton('Data Plans', callback_data='cb_dataPlans'))    
        markup.add(telebot.types.InlineKeyboardButton('Voice and Sms', callback_data='cb_plans:voice:'), telebot.types.InlineKeyboardButton('VA Services' ,callback_data='cb_plans:vas:'))    
        markup.add(telebot.types.InlineKeyboardButton('❌ Cancel', callback_data='cb_cancel'))

        return markup
    else:
        return None

#: Markup for subscribed products
def genMarkup_subscribedPlans(message):
    userId = dbSql.getUserId(message.from_user.id)
    account = dbSql.getDefaultAc(userId)

    if accounts:
        markup = telebot.types.InlineKeyboardMarkup()
        markup.one_time_keyboard=True
        markup.row_width = 2

        ac = ncellapp.ncell(account[1],autoRefresh=True, afterRefresh=[__name__, 'autoRefreshToken'], args=[userId, '__token__'])
        response = ac.subscribedProducts()
        
        #! Success
        if response.responseDescCode == 'BIL2000':
            #! Set status success for use in callback handler
            Response = {'status': 'success'}
            Response['productList'] = response.content['queryAllProductsResponse']['productList']

            responseData = base64.b64encode(str(Response).encode()).decode()
            dbSql.setTempdata(userId, 'responseData', responseData)

            shortButtons =  []
            for i in Response['productList']:
                if len(i['name']) <= 15:
                    shortButtons.append(telebot.types.InlineKeyboardButton(i['name'], callback_data=f"cb_subscribedProductInfo:{i['id']}"))
                else:
                    markup.add(telebot.types.InlineKeyboardButton(i['name'], callback_data=f"cb_subscribedProductInfo:{i['id']}"))
            
            markup.add(*shortButtons)
            markup.add(telebot.types.InlineKeyboardButton('⬅️ Back', callback_data='cb_backToPlans'), telebot.types.InlineKeyboardButton('❌ Cancel' ,callback_data='cb_cancel'))
            
            return markup
        
        #! Invalid refresh token
        elif response.responseDescCode in ['LGN2003', 'LGN2004']:
            Response = response.responseHeader
            Response['status'] = response.responseDescCode

            responseData = base64.b64encode(str(Response).encode()).decode()
            dbSql.setTempdata(userId, 'responseData', responseData)

            return response.responseDescCode
        
        #! Unknown error
        else:
            Response = response.responseHeader
            Response['status'] = 'error'
            Response['statusCode'] = response.statusCode
            
            responseData = base64.b64encode(str(Response).encode()).decode()
            dbSql.setTempdata(userId, 'responseData', responseData)

            return 'unknownError'

    else:
        return None

#: Markup for dataplans catagory
def genMarkup_dataPlans():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.one_time_keyboard=True
    markup.row_width = 2

    markup.add(telebot.types.InlineKeyboardButton('Social Packs' ,callback_data='cb_plans:data:34'), telebot.types.InlineKeyboardButton('Night Data Pack' ,callback_data='cb_plans:data:20'))    
    markup.add(telebot.types.InlineKeyboardButton('Popular Data Services' ,callback_data='cb_plans:data:23'))
    markup.add(telebot.types.InlineKeyboardButton('Non Stop Offers' ,callback_data='cb_plans:data:21'), telebot.types.InlineKeyboardButton('Get More On 4G' ,callback_data='cb_plans:data:19'))    
    markup.add(telebot.types.InlineKeyboardButton('Always On Data Packs' ,callback_data='cb_plans:data:11'))
    markup.add(telebot.types.InlineKeyboardButton('⬅️ Back', callback_data='cb_backToPlans'), telebot.types.InlineKeyboardButton('❌ Cancel' ,callback_data='cb_cancel'))
        
    return markup

#: Markup for products
def genMarkup_products(message):
    userId = dbSql.getUserId(message.from_user.id)
    account = dbSql.getDefaultAc(userId)

    if accounts:
        planType = message.data.split(':')[1]
        catagoryId = message.data.split(':')[2]

        markup = telebot.types.InlineKeyboardMarkup()
        markup.one_time_keyboard=True
        markup.row_width = 2

        ac = ncellapp.ncell(account[1],autoRefresh=True, afterRefresh=[__name__, 'autoRefreshToken'], args=[userId, '__token__'])

        if planType == 'data':
            response = ac.dataPlans(catagoryId)
        elif planType == 'voice':
            response = ac.voiceAndSmsPlans(catagoryId)
        elif planType == 'vas':
            response = ac.vasPlans(catagoryId)

        #! Success
        if response.responseDescCode == 'QAP1000':
            Response = {'status':'success'}
            Response['availablePackages'] = response.content['availablePackages']
            
            responseData = base64.b64encode(str(Response).encode()).decode()
            dbSql.setTempdata(userId, 'responseData', responseData)

            for item in Response['availablePackages']:
                productName = item['displayInfo']['displayName'].replace('Facebook','FB').replace('YouTube','YT').replace('TikTok','TT')
                price = item['productOfferingPrice']['price'].split('.')[0]
                productName += f" (Rs. {price})"

                markup.add(telebot.types.InlineKeyboardButton(text=productName, callback_data=f"cb_productInfo:{item['id']}:{planType}:{catagoryId}"))

            markup.add(telebot.types.InlineKeyboardButton('⬅️ Back', callback_data='cb_dataPlans' if planType=='data' else 'cb_backToPlans'), telebot.types.InlineKeyboardButton('❌ Cancel' ,callback_data='cb_cancel'))
            
            return markup
        
        #! Invalid refresh token
        elif response.responseDescCode in ['LGN2003', 'LGN2004']:
            Response = response.responseHeader
            Response['status'] = response.responseDescCode

            responseData = base64.b64encode(str(Response).encode()).decode()
            dbSql.setTempdata(userId, 'responseData', responseData)

            return response.responseDescCode
        
        #! Unknown error
        else:
            Response = response.responseHeader
            Response['status'] = 'error'
            Response['statusCode'] = response.statusCode
            
            responseData = base64.b64encode(str(Response).encode()).decode()
            dbSql.setTempdata(userId, 'responseData', responseData)

            return 'unknownError'
    else:
        return None
        
#: Free SMS
@bot.message_handler(commands=['freesms'])
def freeSms(message):
    if isSubscribed(message):
        userId = dbSql.getUserId(message.from_user.id)
        if dbSql.getDefaultAc(userId):
            sent = bot.send_message(message.from_user.id, language['enterDestinationMsisdn']['en'], reply_markup=cancelReplyKeyboard())
            bot.register_next_step_handler(sent, sendFreeSms)
        else:
            register(message)

#: Paid SMS
@bot.message_handler(commands=['paidsms'])
def paidsms(message):
    if isSubscribed(message):
        userId = dbSql.getUserId(message.from_user.id)
        if dbSql.getDefaultAc(userId):
            sent = bot.send_message(message.from_user.id, language['enterDestinationMsisdn']['en'], reply_markup=cancelReplyKeyboard())
            bot.register_next_step_handler(sent, sendPaidSms)
        else:
            register(message)

#: SMS type buttons
@bot.message_handler(commands=['sms'])
def sms(message):
    if isSubscribed(message):
        userId = dbSql.getUserId(message.from_user.id)
        if dbSql.getSetting(userId, 'defaultAcId'):
            bot.send_message(message.from_user.id, language['sms']['en'], reply_markup=genMarkup_sms())
        else:
            register(message)

#: SMS Markup
def genMarkup_sms():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.one_time_keyboard=True
    markup.row_width = 2
    markup.add(telebot.types.InlineKeyboardButton('Free SMS', callback_data='cb_freeSms'),
                               telebot.types.InlineKeyboardButton('Paid SMS', callback_data='cb_paidSms'))
    markup.add(telebot.types.InlineKeyboardButton('❌ Cancel', callback_data='cb_cancel'))
    return markup

def sendFreeSms(message):
    if message.text == '❌ Cancel':
        cancelKeyboardHandler(message)
    else:
        dbSql.userId = dbSql.getUserId(message.from_user.id)
        dbSql.setTempdata(dbSql.userId, 'sendSmsTo', message.text)
        sent = bot.send_message(message.from_user.id, language['enterText']['en'], reply_markup=cancelReplyKeyboard())
        
        bot.register_next_step_handler(sent,sendFreeSms2)

def sendFreeSms2(message):
    if message.text == '❌ Cancel':
        cancelKeyboardHandler(message)
    else:
        userId = dbSql.getUserId(message.from_user.id)
        msisdn = dbSql.getTempdata(userId, 'sendSmsTo')
        account = dbSql.getDefaultAc(userId)
        acc = ncellapp.ncell(token=account[1], autoRefresh=True, afterRefresh=[__name__, 'autoRefreshToken'], args=[userId, '__token__'])

        response = acc.sendFreeSms(msisdn, message.text)

        if response.responseDescCode == 'SMS1000':
            #! SMS sent successfully
            if response.content['sendFreeSMSResponse']['statusCode'] == '0':
                bot.send_message(message.from_user.id, language['smsSentSuccessfully']['en'].format(message.text, msisdn), reply_markup=mainReplyKeyboard(message))
                dbSql.setTempdata(userId, 'sendSmsTo', None)

            #! Daily 10 free SMS exceed
            elif response.content['sendFreeSMSResponse']['statusCode'] == '1':
                bot.send_message(message.from_user.id, language['freeSmsExceed']['en'], reply_markup=mainReplyKeyboard(message))
            
            #! Error sending sms (Long text or SMS to own number)
            elif response.content['sendFreeSMSResponse']['statusCode'] == '99':
                bot.send_message(message.from_user.id, language['smsError']['en'], reply_markup=mainReplyKeyboard(message))
            
            #! Error sending SMS to off net numbers
            elif response.content['sendFreeSMSResponse']['statusCode'] == '3':
                bot.send_message(message.from_user.id, language['offnetNumberSmsError']['en'], reply_markup=mainReplyKeyboard(message))
            
            #! Unknown error
            else:
                unknownErrorHandler(message, response.content['sendFreeSMSResponse']['description'], response.content['sendFreeSMSResponse']['statusCode'])

        #! Invalid refresh token
        elif response.responseDescCode in ['LGN2003', 'LGN2004']:
            invalidRefreshTokenHandler(message, userId, response.responseDescCode)
        
        #: Unknown error
        else:
            unknownErrorHandler(message, response.responseDesc, response.statusCode)
            
def sendPaidSms(message):
    if message.text == '❌ Cancel':
        cancelKeyboardHandler(message)
    else:
        userId = dbSql.getUserId(message.from_user.id)
        dbSql.setTempdata(userId, 'sendSmsTo', message.text)
        sent = bot.send_message(message.from_user.id, language['enterText']['en'], reply_markup=cancelReplyKeyboard())
        
        bot.register_next_step_handler(sent,sendPaidSms2)

def sendPaidSms2(message):
    if message.text == '❌ Cancel':
        cancelKeyboardHandler(message)
    else:
        userId = dbSql.getUserId(message.from_user.id)
        msisdn = dbSql.getTempdata(userId, 'sendSmsTo')

        account = dbSql.getDefaultAc(userId)
        acc = ncellapp.ncell(token=account[1], autoRefresh=True, afterRefresh=[__name__, 'autoRefreshToken'], args=[userId, '__token__'])
        
        response = acc.sendSms(msisdn, message.text)
        if response.responseDescCode == 'SMS1000':
            #! SMS sent successfully
            if response.content['sendFreeSMSResponse']['statusCode'] == '0':
                bot.send_message(message.from_user.id, language['smsSentSuccessfully']['en'].format(message.text, msisdn), reply_markup=mainReplyKeyboard(message))
                dbSql.setTempdata(userId, 'sendSmsTo', None)

            #! Error no sufficient balance
            elif response.content['sendFreeSMSResponse']['statusCode'] == '4':
                bot.send_message(message.from_user.id, language['smsErrorInsufficientBalance']['en'], reply_markup=mainReplyKeyboard(message))
            
            #! Error sending sms (Long text or SMS to own number)
            elif response.content['sendFreeSMSResponse']['statusCode'] == '99':
                bot.send_message(message.from_user.id, language['smsError']['en'], reply_markup=mainReplyKeyboard(message))
            
            #! Error sending SMS to off net numbers
            elif response.content['sendFreeSMSResponse']['statusCode'] == '3':
                bot.send_message(message.from_user.id, language['offnetNumberError']['en'], reply_markup=mainReplyKeyboard(message))
            
            #! Unknown error
            else:
                unknownErrorHandler(message, response.content['sendFreeSMSResponse']['description'], response.content['sendFreeSMSResponse']['statusCode'])

        #! Invalid refresh token
        elif response.responseDescCode in ['LGN2003', 'LGN2004']:
            invalidRefreshTokenHandler(message, userId, response.responseDescCode)
        
        #! Unknown error
        else:
            unknownErrorHandler(message, response.responseDesc, response.statusCode)

#: Self recharge
@bot.message_handler(commands=['selfrecharge'])
def selfRecharge(message):
    if isSubscribed(message):
        userId = dbSql.getUserId(message.from_user.id)
        if dbSql.getDefaultAc(userId):
            bot.send_message(message.from_user.id, text=language['rechargeMethod']['en'], reply_markup=genMarkup_rechargeMethod('self'))
        else:
            register(message)

#: Recharge others
@bot.message_handler(commands=['rechargeothers'])
def rechargeOthers(message):
    if isSubscribed(message):
        userId = dbSql.getUserId(message.from_user.id)
        if dbSql.getDefaultAc(userId):
            bot.send_message(message.from_user.id, text=language['rechargeMethod']['en'], reply_markup=genMarkup_rechargeMethod('others'))
        else:
            register(message)

#: Recharge to buttons
@bot.message_handler(commands=['recharge'])
def recharge(message):
    if isSubscribed(message):
        userId = dbSql.getUserId(message.from_user.id)
        if dbSql.getDefaultAc(userId):
            bot.send_message(message.from_user.id, text=language['rechargeTo']['en'], reply_markup=genMarkup_rechargeTo())
        else:
            register(message)

#: Markup for recharge to
def genMarkup_rechargeTo():
    markup = telebot.types.InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(telebot.types.InlineKeyboardButton('Self Recharge', callback_data='cb_selfRecharge'),
                               telebot.types.InlineKeyboardButton('Recharge Others', callback_data='cb_rechargeOthers'))
    markup.add(telebot.types.InlineKeyboardButton('❌ Cancel', callback_data='cb_cancel'))
    
    return markup

#: Markup for recharge methods
def genMarkup_rechargeMethod(rechargeTo):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.one_time_keyboard=True
    markup.row_width = 2
    markup.add(telebot.types.InlineKeyboardButton('Recharge With Pin', callback_data=f'cb_{rechargeTo}RechargePin'),
                               telebot.types.InlineKeyboardButton('Online Recharge', callback_data=f'cb_{rechargeTo}RechargeOnline'))
    markup.add(telebot.types.InlineKeyboardButton('⬅️ Back', callback_data='cb_backToRecharge'),
                               telebot.types.InlineKeyboardButton('❌ Cancel', callback_data='cb_cancel'))

    return markup

#: Self recharge with pin
def selfPinRecharge(message):
    if message.text == '❌ Cancel':
        cancelKeyboardHandler(message)
    else:
        userId = dbSql.getUserId(message.from_user.id)
        account = dbSql.getDefaultAc(userId)

        acc = ncellapp.ncell(token=account[1], autoRefresh=True, afterRefresh=[__name__, 'autoRefreshToken'], args=[userId, '__token__'])
        response = acc.selfRecharge(message.text)

        #! Recharge success
        if 'isRechargeSuccess' in response.content and response.content['isRechargeSuccess'] == True:
            bot.send_message(message.from_user.id, language['rechargeSuccess']['en'], reply_markup=mainReplyKeyboard(message))
        
        #! Incorrect recharge pin
        elif response.responseDescCode == 'MRG2001':
            bot.send_message(message.from_user.id, language['incorrectRpin']['en'], reply_markup=mainReplyKeyboard(message))
        
        #! User black Listed
        elif response.responseDescCode == 'MRG2000':
            bot.send_message(message.from_user.id, language['rechargeBlackListed']['en'], reply_markup=mainReplyKeyboard(message))
        
        #! Invalid refresh token
        elif response.responseDescCode in ['LGN2003', 'LGN2004']:
            invalidRefreshTokenHandler(message, userId, response.responseDescCode)
        
        #! Unknown error
        else:
            unknownErrorHandler(message, response.responseDesc, response.statusCode)

#: Self online recharge
def selfOnlineRecharge(message):
    if message.text == '❌ Cancel':
        cancelKeyboardHandler(message)
    else:
        userId = dbSql.getUserId(message.from_user.id)
    
        account = dbSql.getDefaultAc(userId)
        acc = ncellapp.ncell(token=account[1], autoRefresh=True, afterRefresh=[__name__, 'autoRefreshToken'], args=[userId, '__token__'])
        
        response = acc.onlineRecharge(message.text)

        #! Success
        if response.responseDescCode == 'OPS1000':
            bot.send_message(message.from_user.id, text=f"<a href='{response.content['url']}'>Click here</a> and complete the payment.", reply_markup=mainReplyKeyboard(message))
        
        #! Recharge amount is less than zero
        elif response.responseDescCode in ['OPS2000','OPS2011']:
            bot.send_message(message.from_user.id, language['amountLessThanZeroError']['en'], reply_markup=mainReplyKeyboard(message))
        
        #! Recharge amount is more than 5000
        elif response.responseDescCode == 'OPS2012':
            bot.send_message(message.from_user.id, language['amountMoreThan5000Error']['en'], reply_markup=mainReplyKeyboard(message))

        #! Invalid refresh token
        elif response.responseDescCode in ['LGN2003', 'LGN2004']:
            invalidRefreshTokenHandler(message, userId, response.responseDescCode)
        
        #! Unknown error
        else:
            unknownErrorHandler(message, response.responseDesc, response.statusCode)

#: Recharge others with pin
def rechargeOthersPin(message):
    if message.text == '❌ Cancel':
        cancelKeyboardHandler(message)
    else:
        userId = dbSql.getUserId(message.from_user.id)
        dbSql.setTempdata(userId, 'rechargeTo', message.text)

        sent = bot.send_message(message.from_user.id,language['enterRechargePin']['en'], reply_markup=cancelReplyKeyboard())
        
        bot.register_next_step_handler(sent,rechargeOthersPin2)

def rechargeOthersPin2(message):
    if message.text == '❌ Cancel':
        cancelKeyboardHandler(message)
    else:
        userId = dbSql.getUserId(message.from_user.id)
        msisdn = dbSql.getTempdata(userId, 'rechargeTo')
        account = dbSql.getDefaultAc(userId)
        acc = ncellapp.ncell(token=account[1], autoRefresh=True, afterRefresh=[__name__, 'autoRefreshToken'], args=[userId, '__token__'])
        
        response = acc.recharge(msisdn, message.text)

        if 'isRechargeSuccess' in response.content:
            #! Success
            if response.content['isRechargeSuccess']:
                bot.send_message(message.from_user.id, language['rechargeSuccess']['en'], reply_markup=mainReplyKeyboard(message))
            
            #? For recharge others, ncell response with same responsecode. So, compairing with description.
            # FIX THIS NCELL :))
            elif response.responseDesc == 'MSISDN does not exist.':
                bot.send_message(message.from_user.id, language['invalidNumber']['en'], reply_markup=mainReplyKeyboard(message))
            elif response.responseDesc == 'The user is in black list.':
                bot.send_message(message.from_user.id, language['rechargeOBlackListed']['en'], reply_markup=mainReplyKeyboard(message))
            elif response.responseDesc == 'the password cannot be found in online vc':
                bot.send_message(message.from_user.id, language['incorrectRpin']['en'], reply_markup=mainReplyKeyboard(message))
            #! Unknown error
            else:
                unknownErrorHandler(message, response.responseDesc, response.responseCode)
        
        #! Invalid refresh token
        elif response.responseDescCode in ['LGN2003', 'LGN2004']:
            invalidRefreshTokenHandler(message, userId, response.responseDescCode)
        
        #! Unknown error
        else:
            unknownErrorHandler(message, response.responseDesc, response.statusCode)
        
#: Recharge others online
def rechargeOthersOnline(message):
    if message.text == '❌ Cancel':
        cancelKeyboardHandler(message)
    else:
        userId = dbSql.getUserId(message.from_user.id)
        dbSql.setTempdata(userId, 'rechargeTo', message.text)
        sent = bot.send_message(message.from_user.id, language['enterRechargeAmount']['en'], reply_markup=cancelReplyKeyboard())
        
        bot.register_next_step_handler(sent, rechargeOthersOnline2)

def rechargeOthersOnline2(message):
    if message.text == '❌ Cancel':
        cancelKeyboardHandler(message)
    else:
        userId = dbSql.getUserId(message.from_user.id)
        msisdn = dbSql.getTempdata(userId, 'rechargeTo')
        
        account = dbSql.getDefaultAc(userId)
        acc = ncellapp.ncell(token=account[1], autoRefresh=True, afterRefresh=[__name__, 'autoRefreshToken'], args=[userId, '__token__'])
        
        response = acc.onlineRecharge(message.text, msisdn)

        #! Success
        if response.responseDescCode == 'OPS1000':
            bot.send_message(message.from_user.id, text=f"<a href='{response.content['url']}'>Click here</a> and complete the payment.", reply_markup=mainReplyKeyboard(message))
        
        #! Invalid number
        elif response.responseDescCode in ['OPS2104', 'OPS2003']:
            bot.send_message(message.from_user.id, language['invalidNumber']['en'], reply_markup=mainReplyKeyboard(message))
        
        #! Recharge amount is less than zero
        elif response.responseDescCode in ['OPS2000','OPS2011']:
            bot.send_message(message.from_user.id, language['amountLessThanZeroError']['en'], reply_markup=mainReplyKeyboard(message))
        
        #! Recharge amount is more than 5000
        elif response.responseDescCode == 'OPS2012':
            bot.send_message(message.from_user.id, language['amountMoreThan5000Error']['en'], reply_markup=mainReplyKeyboard(message))

        #! Invalid refresh token
        elif response.responseDescCode in ['LGN2003', 'LGN2004']:
            invalidRefreshTokenHandler(message, userId, response.responseDescCode)
        
        #! Unknown error
        else:
            unknownErrorHandler(message, response.responseDesc, response.statusCode)

#: Callback handler
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    #! Cancel a process
    if call.data == 'cb_cancel':
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.id, text='❌ Cancelled')
    
    #! Check whether a user is subscribed or not after clicking button
    elif call.data[:15] == 'cb_isSubscribed':
        if isSubscribed(call, sendMessage=False):
            callingFunction = call.data.split(':')[1]
            
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.id, text=language['thanksForSub']['en'])
            
            #!? Executing the calling function
            globals()[callingFunction](call)
            
        else:
            bot.answer_callback_query(call.id, language['notSubscribedCallback']['en'])

   #! Select action for /accounts     
    elif call.data == 'cb_selectAccount':
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.id, text=language['accounts']['en'], reply_markup=genMarkup_accounts(message=call, action='select'))

    #! Remove action for /accounts
    elif call.data == 'cb_removeAccount':
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.id, text=language['accounts']['en'], reply_markup=genMarkup_accounts(message=call, action='remove'))
    
    #! Select default account
    elif call.data[:17] == 'cb_selectAccount_':
        userId = dbSql.getUserId(call.from_user.id)
        
        #! MSISDN and Account Id is after 17th index of callback data
        msisdn = call.data[17:].split(':')[0]
        
        accountId = call.data[17:].split(':')[1]
        defaultAcId = dbSql.getSetting(userId, 'defaultAcID')
        
        #! If the account is already default account
        if str(defaultAcId) == accountId:
            bot.answer_callback_query(call.id, language['alreadyLoggedin']['en'].format(msisdn))
        else:
            dbSql.setDefaultAc(userId, accountId)
            bot.answer_callback_query(call.id, f"{language['loggedinAs']['en'].format(msisdn)}")
            bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.id, reply_markup=genMarkup_accounts(call, 'select'))

    #! Remove account from database
    elif call.data[:17] == 'cb_removeAccount_':
        userId = dbSql.getUserId(call.from_user.id)

        msisdn = call.data[17:].split(':')[0]
        accountId = call.data[17:].split(':')[1]

        dbSql.deleteAccount(userId, accountId)
        bot.answer_callback_query(call.id, f"{language['successfullyLoggedout']['en'].format(msisdn)}")

        markup = genMarkup_accounts(message=call, action='remove')
        if markup:
            bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.id, reply_markup=genMarkup_accounts(message=call, action='remove'))
        else:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.id, text=language['noAccounts']['en'])

    #! Re-enter the OTP
    elif call.data == 'cb_reEnterOtp':
        sent = bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.id, text=language['enterOtp']['en'])
        bot.register_next_step_handler(sent, getToken)

    #! Re-sent the OTP to the given number
    elif call.data == 'cb_reSendOtp':
        getOtp(message=call, called=True)
    
    #! Change the register number
    elif call.data == 'cb_changeRegisterNumber':
        sent = bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.id, text=language['enterNumber']['en'])
        bot.register_next_step_handler(sent, getOtp)
    
    #! Callback handler for Regigter with Cancel keyboard
    elif call.data == 'cb_registerNumber':
        bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.id)
        register(call)
    
    #! Self recharge
    elif call.data == 'cb_selfRecharge':
        bot.edit_message_text(chat_id=call.message.chat.id,message_id=call.message.id,text=language['rechargeMethod']['en'],reply_markup=genMarkup_rechargeMethod('self'))
    
    #! Recharge Others
    elif call.data == 'cb_rechargeOthers':
        bot.edit_message_text(chat_id=call.message.chat.id,message_id=call.message.id,text=language['rechargeMethod']['en'], reply_markup=genMarkup_rechargeMethod('others'))
    
    #! Self recharge with pin
    elif call.data == 'cb_selfRechargePin':
        bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.id)
        sent = bot.send_message(chat_id=call.message.chat.id, text=language['enterRechargePin']['en'], reply_markup=cancelReplyKeyboard())
        bot.register_next_step_handler(sent, selfPinRecharge)
    
    #! Self recharge online
    elif call.data == 'cb_selfRechargeOnline':
        bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.id)
        sent = bot.send_message(chat_id=call.message.chat.id, text=language['enterRechargeAmount']['en'], reply_markup=cancelReplyKeyboard())
        bot.register_next_step_handler(sent, selfOnlineRecharge)
    
    #! Recharge others with pin
    elif call.data == 'cb_othersRechargePin':
        bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.id)
        sent = bot.send_message(chat_id=call.message.chat.id ,text=language['enterDestinationMsisdn']['en'], reply_markup=cancelReplyKeyboard())
        bot.register_next_step_handler(sent, rechargeOthersPin)
    
    #! Recharge others with pin
    elif call.data == 'cb_othersRechargeOnline':
        bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.id)
        sent = bot.send_message(chat_id=call.message.chat.id, text=language['enterDestinationMsisdn']['en'], reply_markup=cancelReplyKeyboard())
        bot.register_next_step_handler(sent, rechargeOthersOnline)
    
    #! Back to recharge menu
    elif call.data == 'cb_backToRecharge':
        userId = dbSql.getUserId(call.from_user.id)
        if dbSql.getDefaultAc(userId):
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.id, text=language['rechargeTo']['en'], reply_markup=genMarkup_rechargeTo())
        else:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.id, text=language['noAccounts']['en'], reply_markup=mainReplyKeyboard(call))

    #! Alert before taking loans
    elif call.data == 'cb_confirmLoan':
        loan(message=call, called=True)

    #! Take loan
    elif call.data == 'cb_takeLoan':
        userId = dbSql.getUserId(call.from_user.id)

        account = dbSql.getDefaultAc(userId)
        acc = ncellapp.ncell(token=account[1], autoRefresh=True, afterRefresh=[__name__, 'autoRefreshToken'], args=[userId, '__token__'])

        response = acc.takeLoan()
        
        #! Loan success
        if response.responseDescCode == 'CL1003':
            bot.answer_callback_query(call.id, language['loanGranted']['en'], show_alert=True)
        
        #! Loan failled
        elif response.responseDescCode == 'CL3001':
            bot.answer_callback_query(call.id, language['loanFailled']['en'], show_alert=True)
        
        #! Invalid refresh token
        elif response.responseDescCode in ['LGN2003', 'LGN2004']:
            invalidRefreshTokenHandler_cb(call, userId, response.responseDescCode)
        
        #! Unknown error
        else:
            UnknownErrorHandler_cb(call, response.responseDesc, response.statusCode)
        
    #! Back to balance
    elif call.data == 'cb_backToBalance':
        balance(message=call, called=True)

    #! Send free SMS
    elif call.data == 'cb_freeSms':
        bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.id)
        freeSms(message=call)
    
    #! Send paid SMS
    elif call.data == 'cb_paidSms':
        bot.delete_message(chat_id=call.message.chat.id, message_id=call.message.id)
        paidsms(message=call)

    #! Subscribed plans
    elif call.data == 'cb_subscribedPlans':
        markup = genMarkup_subscribedPlans(call)
        userId = dbSql.getUserId(call.from_user.id)

        #!? First check if the markup contains error or not 
        if markup in [ 'LGN2003', 'LGN2004']:
            invalidRefreshTokenHandler_cb(call, userId, responseCode=markup)
                
        elif markup == 'unknownError':
            #! Response data is stored in database in b64 encoded form
            encodedResponse = dbSql.getTempdata(userId, 'responseData')
            decodedResponse = base64.b64decode(encodedResponse.encode()).decode()

            response = ast.literal_eval(decodedResponse)
            UnknownErrorHandler_cb(call, response['responseDesc'], response['statusCode'])
        
        #!? If no error, send reply markup
        else:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.id, text=language['subscribedPlans']['en'] if markup else language['noAccounts']['en'], reply_markup=markup)

    #! Subscribed product info
    elif call.data[:24] == 'cb_subscribedProductInfo':
        productId = call.data.split(':')[1]
        userId = dbSql.getUserId(call.from_user.id)

        #! Response data is stored in database in b64 encoded form
        encodedResponse = dbSql.getTempdata(userId, 'responseData')
        decodedResponse = base64.b64decode(encodedResponse.encode()).decode()

        response = ast.literal_eval(decodedResponse)

        if response['status'] == 'success':
            response = response['productList']
            #! Iterate through the response to find the product 
            productInfo = None
            for i in response:
                if i['id'] == productId:
                    productInfo = i
                    break
            
            if productInfo:
                markup = telebot.types.InlineKeyboardMarkup()
                markup.one_time_keyboard=True
                markup.row_width = 2

                markup.add(telebot.types.InlineKeyboardButton(text='Deactivate' if i['isDeactivationAllowed'] == 1 else '⛔ Deactivate', callback_data=f"cb_deactivatePlan:{i['subscriptionCode']}" if i['isDeactivationAllowed'] == 1 else 'cb_deactivationNotAllowed'))
                markup.add(telebot.types.InlineKeyboardButton('⬅️ Back' ,callback_data='cb_subscribedPlans'), telebot.types.InlineKeyboardButton('❌ Cancel' ,callback_data='cb_cancel'))
            
                text = f"<b>{productInfo['name']}</b>\n\n<em>{productInfo['description']}\n\nSubscribed On: {productInfo['subscriptionDate']}\nExpiry Date: {productInfo['expiryDate']}\n</em>"
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.id, text=text, reply_markup=markup)

            else:
                bot.answer_callback_query(call.id, language['somethingWrong']['en'])
        
        #! Invalid refresh token
        elif response['status'] in ['LGN2003', 'LGN2004']:
            invalidRefreshTokenHandler_cb(call, userId, response['status'])
        
        #! Unknown error
        else:
            UnknownErrorHandler_cb(call, response['responseDesc'], response['statusCode'])

    #! Data plans Catagory
    elif call.data == 'cb_dataPlans':
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.id, text=language['selectPlanType']['en'], reply_markup=genMarkup_dataPlans())

    #! Product list
    elif call.data[:8] == 'cb_plans':
        markup = genMarkup_products(call)
        userId = dbSql.getUserId(call.from_user.id)
        if markup in [ 'LGN2003', 'LGN2004']:
            invalidRefreshTokenHandler_cb(call, userId, responseCode=markup)
                
        elif markup == 'unknownError':
            #! Response data is stored in database in b64 encoded form
            encodedResponse = dbSql.getTempdata(userId, 'responseData')
            decodedResponse = base64.b64decode(encodedResponse.encode()).decode()

            response = ast.literal_eval(decodedResponse)
            UnknownErrorHandler_cb(call, response['responseDesc'], response['statusCode'])
        
        #! Send reply markup if no errors
        else:
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.id, text=language['selectProduct']['en'] if markup else language['noAccounts']['en'], reply_markup=markup)
    
    #! Product info
    elif call.data[:14] == 'cb_productInfo':
        productId = call.data.split(':')[1]
        userId = dbSql.getUserId(call.from_user.id)

        #! Response data is stored in database in b64 encoded form
        encodedResponse = dbSql.getTempdata(userId, 'responseData')
        decodedResponse = base64.b64decode(encodedResponse.encode()).decode()

        response = ast.literal_eval(decodedResponse)

        if response['status'] == 'success':
            response = response['availablePackages']
            #! Iterate through the response to find the product 
            productInfo = None
            for i in response:
                if i['id'] == productId:
                    productInfo = i
                    break
            
            if productInfo:
                planType = call.data.split(':')[2]
                catagoryId = call.data.split(':')[3]
                markup = telebot.types.InlineKeyboardMarkup()
                markup.one_time_keyboard=True
                markup.row_width = 2

                markup.add(telebot.types.InlineKeyboardButton(text='Activate' if productInfo['isBalanceSufficient'] else '⛔ Activate', callback_data=f"cb_activatePlan:{productInfo['techInfo']['subscriptionCode']}" if productInfo['isBalanceSufficient'] else 'cb_noEnoughBalanceToSub'))
                markup.add(telebot.types.InlineKeyboardButton('⬅️ Back' ,callback_data=f'cb_plans:{planType}:{catagoryId}'), telebot.types.InlineKeyboardButton('❌ Cancel' ,callback_data='cb_cancel'))

                summary = '</em>\nSummery:\n<em>' if productInfo['accounts'] else ''
                
                for i in productInfo['accounts']:
                    summary += f"👉 {i['name']} {i['amount']} {i['amountUom']} valid for {i['validity']}{i['validityUom']}\n"
                
                summary += f"\n💰 {productInfo['productOfferingPrice']['priceUom']} {'' if productInfo['productOfferingPrice']['priceUom'] == 'FREE' else productInfo['productOfferingPrice']['price']} {'' if productInfo['productOfferingPrice']['priceUom'] == 'FREE' else productInfo['productOfferingPrice']['priceType']}"

                text = f"<b>{productInfo['displayInfo']['displayName']}</b>\n\n<em>{productInfo['displayInfo']['description']}\n{summary}</em>"
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.id, text=text, reply_markup=markup)

            else:
                bot.answer_callback_query(call.id, language['somethingWrong']['en'])
        
        #! Invalid refresh token
        elif response['status'] in ['LGN2003', 'LGN2004']:
            invalidRefreshTokenHandler_cb(call, userId, response['status'])
        
        #! Unknown error
        else:
            UnknownErrorHandler_cb(call, response['responseDesc'], response['statusCode'])

    #! Deactivation not allowed
    elif call.data == 'cb_deactivationNotAllowed':
        bot.answer_callback_query(call.id, language['deactivationNotAllowed']['en'], show_alert=True)

    #! No enough balance to subscribe
    elif call.data == 'cb_noEnoughBalanceToSub':
        bot.answer_callback_query(call.id, language['noEnoughBalanceToSub']['en'], show_alert=True)

    #: Deactivate product
    elif call.data[:17] == 'cb_deactivatePlan':
        subscriptionCode = call.data[18:]
        userId = dbSql.getUserId(call.from_user.id)

        account = dbSql.getDefaultAc(userId)
        acc = ncellapp.ncell(token=account[1], autoRefresh=True, afterRefresh=[__name__, 'autoRefreshToken'], args=[userId, '__token__'])

        response = acc.unsubscribeProduct(subscriptionCode)

        #! Success
        if response.responseDescCode == 'BIL1001':
            bot.answer_callback_query(call.id, language['deactivationSuccessful']['en'], show_alert=True)
        
        #! Product already deactivated
        elif response.responseDescCode == 'PSU2004':
            bot.answer_callback_query(call.id, language['alreadyDeactivated']['en'], show_alert=True)
        
        #! Product already deactivated
        elif response.responseDescCode in ['LGN2003', 'LGN2004']:
            invalidRefreshTokenHandler(message, userId, response.responseDescCode)
        
        #! Unknown error
        else:
            UnknownErrorHandler_cb(call, response.responseDesc, response.statusCode)

    #: Activate product
    elif call.data[:15] == 'cb_activatePlan':
        subscriptionCode = call.data[16:]

        userId = dbSql.getUserId(call.from_user.id)

        account = dbSql.getDefaultAc(userId)
        acc = ncellapp.ncell(token=account[1], autoRefresh=True, afterRefresh=[__name__, 'autoRefreshToken'], args=[userId, '__token__'])

        response = acc.subscribeProduct(subscriptionCode)

        #! Success
        if response.responseDescCode == 'BIL1000':
            bot.answer_callback_query(call.id, language['activationSuccessful']['en'], show_alert=True)

        #! Product already activated
        if response.responseDescCode == 'PSU2003':
            bot.answer_callback_query(call.id, language['alreadyActivated']['en'], show_alert=True)
        
        #! Invalid refresh token
        elif response.responseDescCode in ['LGN2003', 'LGN2004']:
            invalidRefreshTokenHandler(message, userId, response.responseDescCode)
        
        #! Unknown error
        else:
            UnknownErrorHandler_cb(call, response.responseDesc, response.statusCode)

    #! Go back to plan catagory
    elif call.data == 'cb_backToPlans':
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.id, text=language['selectPlanType']['en'], reply_markup=genMarkup_plans(call) )

@bot.message_handler(content_types=['text'])
def replyKeyboard(message):
    if message.text == '➕ Register':
        register(message)
    
    elif message.text == '💬 SMS':
        sms(message)

    elif message.text == '👥 Accounts':
        accounts(message)

    elif message.text == '💳 Recharge':
        recharge(message)
    
    elif message.text == '💰 Balance':
        balance(message)

    elif message.text == '📦 Plans':
        plans(message)

    elif message.text == '🔃 Switch':
        switch(message)
      
    elif message.text in ['⚙️ Settings', '/settings']:
        text = language['settingsMenu']['en']
        bot.send_message(message.from_user.id, text)

    elif message.text in ['❌ Cancel','/cancel'] :
        bot.send_message(message.from_user.id, language['cancelled']['en'], reply_markup=mainReplyKeyboard(message))

    elif message.text in ['⁉️ Help', '/help']:
        bot.send_message(message.from_user.id, language['helpMenu']['en'])

    elif message.text in ['🎁 Support Us', '/support']:
        bot.send_message(message.from_user.id, language['supportUsMenu']['en'])
    
    else:
        bot.send_message(message.from_user.id, language['helpMenu']['en'])

#: Polling
if config['telegram']['connectionType'] == 'polling':
    #! Remove previous webhook if exists
    bot.remove_webhook()
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            #! Logging the error
            logger.error(e, exc_info=True)
            #! Printing the error
            loggerConsole.error(e, exc_info=True)

#: Webhook
elif config['telegram']['connectionType'] == 'webhook':
    #! Set webhook
    bot.set_webhook(url=webhookBaseUrl + webhookUrlPath,
                    certificate=open(config['telegram']['webhookOptions']['sslCertificate'], 'r'))

    #! Build ssl context
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    context.load_cert_chain(config['telegram']['webhookOptions']['sslCertificate'], config['telegram']['webhookOptions']['sslPrivatekey'])

    #! Start aiohttp server
    web.run_app(
        app,
        host=config['telegram']['webhookOptions']['webhookListen'],
        port=config['telegram']['webhookOptions']['webhookPort'],
        ssl_context=context,
    )