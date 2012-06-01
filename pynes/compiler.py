# -*- coding: utf-8 -*-

from analyzer import analyse
from c6502 import opcodes, address_mode_def
from re import match

import inspect
from binascii import hexlify

from directives import directive_list

from cartridge import Cartridge

asm65_tokens = [
    dict(type='T_INSTRUCTION', regex=r'^(ADC|AND|ASL|BCC|BCS|BEQ|BIT|BMI|BNE|BPL|BRK|BVC|BVS|CLC|CLD|CLI|CLV|CMP|CPX|CPY|DEC|DEX|DEY|EOR|INC|INX|INY|JMP|JSR|LDA|LDX|LDY|LSR|NOP|ORA|PHA|PHP|PLA|PLP|ROL|ROR|RTI|RTS|SBC|SEC|SED|SEI|STA|STX|STY|TAX|TAY|TSX|TXA|TXS|TYA)', store=True),
    dict(type='T_ADDRESS', regex=r'\$([\dA-F]{2,4})', store=True),
    dict(type='T_HEX_NUMBER', regex=r'\#\$?([\dA-F]{2})', store=True), #TODO: change to HEX_NUMBER
    dict(type='T_BINARY_NUMBER', regex=r'\#%([01]{8})', store=True), #TODO: change to BINARY_NUMBER
    dict(type='T_STRING', regex=r'^"[^"]*"', store=True),
    dict(type='T_SEPARATOR', regex=r'^,', store=True),
    dict(type='T_REGISTER', regex=r'^(X|x|Y|y)', store=True),
    dict(type='T_OPEN', regex=r'^\(', store=True),
    dict(type='T_CLOSE', regex=r'^\)', store=True),
    dict(type='T_LABEL', regex=r'^([a-zA-Z][a-zA-Z\d]*)\:', store=True),
    dict(type='T_MARKER', regex=r'^[a-zA-Z][a-zA-Z\d]*', store=True),
    dict(type='T_DIRECTIVE', regex=r'^\.[a-z]+', store=True),
    dict(type='T_DECIMAL_ARGUMENT', regex=r'^[\d]+', store=True),
    dict(type='T_ENDLINE', regex=r'^\n', store=True),
    dict(type='T_WHITESPACE', regex=r'^[ \t\r]+', store=False),
    dict(type='T_COMMENT', regex=r'^;[^\n]*', store=False)
]

def look_ahead(tokens, index, type, value = None):
    if index > len(tokens) - 1:
        return 0
    token = tokens[index]
    if token['type'] == type:
        if value == None or token['value'].upper() == value.upper():
            return 1
    return 0

def t_endline (tokens, index):
    return look_ahead(tokens, index, 'T_ENDLINE', '\n')

def t_directive (tokens, index):
    return look_ahead(tokens, index, 'T_DIRECTIVE')

def t_directive_argument(tokens, index):
    return OR([t_decimal_argument, t_address, t_marker, t_string], tokens, index)

def t_decimal_argument(tokens, index):
    return look_ahead(tokens, index, 'T_DECIMAL_ARGUMENT')

def t_relative (tokens, index):
    if (look_ahead(tokens, index, 'T_INSTRUCTION') and 
        tokens[index]['value'] in [
            'BCC', 'BCS', 'BEQ', 'BNE',
            'BMI', 'BPL', 'BVC', 'BVS'
        ]):
        return 1
    return 0

def t_instruction (tokens, index):
    return look_ahead(tokens, index, 'T_INSTRUCTION')

def t_zeropage (tokens,index):
    lh = look_ahead(tokens, index, 'T_ADDRESS')
    if lh and len(tokens[index]['value']) == 3:
        return 1
    return 0

def t_label(tokens, index):
    return look_ahead(tokens, index, 'T_LABEL')

def t_marker(tokens, index):
    return look_ahead(tokens, index, 'T_MARKER')

def t_address(tokens, index):
    return look_ahead(tokens, index, 'T_ADDRESS')

def t_string(tokens, index):
    return look_ahead(tokens, index, 'T_STRING')

def t_address_or_t_marker(tokens, index):
    return OR([t_address, t_marker], tokens, index)

def t_hex_number(tokens, index):
    return look_ahead(tokens, index, 'T_HEX_NUMBER')

def t_binary_number(tokens, index):
    return look_ahead(tokens, index, 'T_BINARY_NUMBER')

def t_number(tokens, index):
    return OR([t_hex_number, t_binary_number], tokens, index)

def t_separator(tokens , index):
    return look_ahead(tokens, index, 'T_SEPARATOR')

def t_register_x(tokens, index):
    return look_ahead(tokens, index, 'T_REGISTER', 'X')

def t_register_y(tokens, index):
    return look_ahead(tokens, index, 'T_REGISTER', 'Y')

def t_open(tokens, index):
    return look_ahead(tokens, index, 'T_OPEN', '(')

def t_close(tokens, index):
    return look_ahead(tokens, index, 'T_CLOSE', ')')

def t_list(tokens, index):
    if t_address(tokens, index) and t_separator(tokens, index+1):
        arg = 0
        islist = True
        return True
        #TODO
        while not t_endline(tokens, (index + (arg * 2) + 1)):
            islist = islist & t_address(tokens, index + (arg * 2))
            islist = islist & t_separator(tokens, index + (arg * 2) + 1)
            arg += 1
    return False

def get_list_jump(tokens, index):
    keep = True
    a = 0
    while keep:
        keep = keep & (
                t_address(tokens, index + a) |
                t_separator(tokens, index + a)
            )
        a += 1
    return a

def OR(args, tokens, index):
    for t in args:
        if t(tokens, index):
            return 1
    return 0

asm65_bnf = [
    dict(type='S_RELATIVE', short='rel', bnf=[t_relative, t_address_or_t_marker]),
    dict(type='S_IMMEDIATE', short='imm', bnf=[t_instruction, t_number]),
    dict(type='S_ZEROPAGE_X', short='zpx', bnf=[t_instruction, t_zeropage, t_separator, t_register_x]),
    dict(type='S_ZEROPAGE_Y', short='zpy', bnf=[t_instruction, t_zeropage, t_separator, t_register_y]),
    dict(type='S_ZEROPAGE', short='zp', bnf=[t_instruction, t_zeropage]),
    dict(type='S_ABSOLUTE_X', short='absx', bnf=[t_instruction, t_address_or_t_marker, t_separator, t_register_x]),
    dict(type='S_ABSOLUTE_Y', short='absy', bnf=[t_instruction, t_address_or_t_marker, t_separator, t_register_y]),
    dict(type='S_ABSOLUTE', short='abs', bnf=[t_instruction, t_address_or_t_marker]),
    dict(type='S_INDIRECT_X', short='indx', bnf=[t_instruction, t_open, t_address_or_t_marker, t_separator, t_register_x, t_close]),
    dict(type='S_INDIRECT_Y', short='indy', bnf=[t_instruction, t_open, t_address_or_t_marker, t_close, t_separator, t_register_y]),
    dict(type='S_IMPLIED', short='sngl', bnf=[t_instruction]),
    #TODO dict(type='S_DIRECTIVE', short='sngl', bnf=[t_directive, [OR, t_num, t_address]]),
]

def lexical(code):
    return analyse(code, asm65_tokens)

def get_int_value(token, labels = []):
    if token['type'] == 'T_ADDRESS':
        m = match(asm65_tokens[1]['regex'], token['value'])
        return int(m.group(1), 16)
    if token['type'] == 'T_HEX_NUMBER':
        m = match(asm65_tokens[2]['regex'], token['value'])
        return int(m.group(1), 16)
    elif token['type'] == 'T_BINARY_NUMBER':
        m = match(asm65_tokens[3]['regex'], token['value'])
        return int(m.group(1), 2)
    elif token['type'] == 'T_MARKER':
        return labels[token['value']]

def get_label(number_token):
    m = match(asm65_tokens[9]['regex'], number_token)
    if m:
        return m.group(1)
    raise Exception('Invalid Label')

def syntax(t):
    ast = []
    x = 0 # consumed
    debug = 0
    labels = []
    while (x < len(t)):
        if t_directive(t,x) and t_list(t, x+1):
            leaf = {}
            leaf['type'] = 'S_DIRECTIVE'
            leaf['directive'] = t[x]
            end = get_list_jump(t,x+1)
            leaf['args'] = dict(
                type = 'S_LIST',
                elements = t[ x: x+end]
            ) 
            ast.append(leaf)
            x += end
        elif t_directive(t,x) and t_directive_argument(t,x+1):
            leaf = {}
            leaf['type'] = 'S_DIRECTIVE'
            leaf['directive'] = t[x]
            leaf['args'] = t[x+1]
            ast.append(leaf)
            x += 2
        elif t_label(t,x):
            labels.append(get_label(t[x]['value']))
            x += 1
        elif t_endline(t,x):
            x += 1
        else:
            for bnf in asm65_bnf:
                leaf = {}
                look_ahead = 0
                move = False
                for i in bnf['bnf']:
                    move = i(t,x + look_ahead)
                    if not move:
                        break;
                    look_ahead += 1
                if move:
                    if len(labels) > 0:
                        leaf['labels'] = labels
                        labels = []
                    size = 0;
                    walk = 0;
                    for b in bnf['bnf']:
                        size += b(t,x+walk)
                        walk += 1
                    leaf['children'] = t[x: x+size]
                    leaf['type'] = bnf['type']
                    leaf['short'] = bnf['short']
                    ast.append(leaf)
                    x += look_ahead
                    break;
        debug += 1
        if debug > 10000:
            print t[x]
            raise Exception('Infinity Loop')
    return ast

def semantic(ast, iNES=False):
    cart = Cartridge()
    labels = {}
    #find all labels o the symbol table
    labels['palette'] = 0xE000 #TODO stealing on test
    labels['sprites'] = 0xE000 + 32 #TODO stealing on test
    address = 0
    for leaf in ast:
        if leaf['type'] == 'S_DIRECTIVE':
            directive = leaf['directive']['value']
            if '.org' == directive:
                address = int(leaf['args']['value'][1:], 16)
        if 'labels' in leaf:
            for label in leaf['labels']:
                labels[label] = address
        if leaf['type'] != 'S_DIRECTIVE':
            size =  address_mode_def[leaf['short']]['size']
            address += size

    #translate statments to opcode
    bank_id = 0
    for leaf in ast:
        print leaf
        if leaf['type'] == 'S_DIRECTIVE':
            directive = leaf['directive']['value']
            if 'T_DECIMAL_ARGUMENT' == leaf['args']['type']:
                args = leaf['args']['value']
                num = int(args)
                directive_list[directive](num, cart)
            elif 'T_ADDRESS' == leaf['args']['type']:
                address = int(leaf['args']['value'][1:], 16)
                directive_list[directive](address, cart)
            elif 'T_MARKER' == leaf['args']['type']:
                address = get_int_value(leaf['args'], labels)
                directive_list[directive](address, cart)
            elif 'T_STRING' == leaf['args']['type']:
                string = leaf['args']['value'][1:-1]
                directive_list[directive](string, cart)
            elif 'S_LIST' == leaf['args']['type']:
                elements = leaf['args']['elements']
                directive_list[directive](elements, cart)
        else:
            if leaf['type'] == 'S_IMPLIED':
                instruction = leaf['children'][0]['value']
                address = False
            elif leaf['type'] in ['S_RELATIVE', 'S_IMMEDIATE', 'S_ZEROPAGE', 'S_ABSOLUTE']:
                instruction = leaf['children'][0]['value']
                address = get_int_value(leaf['children'][1], labels)
            elif leaf['type'] in ['S_ZEROPAGE_X', 'S_ZEROPAGE_Y', 'S_ABSOLUTE_X', 'S_ABSOLUTE_Y']:
                instruction = leaf['children'][0]['value']
                address = get_int_value(leaf['children'][1], labels)
            elif leaf['type'] in ['S_INDIRECT_X', 'S_INDIRECT_Y']:
                instruction = leaf['children'][0]['value']
                address = get_int_value(leaf['children'][2], labels)

            #instruction = leaf['instruction']['value']
            address_mode = leaf['short']
            opcode = opcodes[instruction][address_mode]
            if address_mode != 'sngl':
                #address = get_int_value(leaf['arg'], labels)

                if 'rel' == address_mode:
                    address = 126 + (address - cart.pc)
                    if address == 128:
                        address = 0
                    elif address < 128:
                        address = address | 0b10000000
                    elif address > 128:
                        address = address & 0b01111111

                if address_mode_def[address_mode]['size'] == 2:
                    cart.append_code([opcode, address])
                else:
                    arg1 = (address & 0x00ff)
                    arg2 = (address & 0xff00) >> 8
                    cart.append_code([opcode, arg1, arg2])
            else:
                cart.append_code([opcode])
    nes_code = []
    if iNES:
        return cart.get_ines_code()
    else:
        return cart.get_code()


def main():
    print 'yo'

if __name__ == '__main__':
    main()