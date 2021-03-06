import os
import tempfile

import CRFPP

import config
from jpype import *

from bin.jvm_crf_dic import HanlpJvm
from bin.term_tuple import AbbrChar
from load.load_model import get_model_abbr, RecCom
from util.tool import NLPDriver, get_closest_file


class RegCom:
    def __init__(self, modelfile=None, nbest=None,):
        if not nbest:
            nbest = 1
        if not modelfile:
            assert False
        self.tagger = CRFPP.Tagger('-n '+str(nbest)+' -m ' + modelfile)
        self.tagger.clear()
        self.begin = "#SENT_BEG#\tbegin\tOUT"
        self.end = "#SENT_BEG#\tend\tOUT"
        self.terms = []

    def _add(self, atts):
        result = str(atts)
        self.tagger.add(result)

    def addterms(self, termlist):
        self._add(self.begin)
        for term in termlist:
            self._add(term)
        self._add(self.end)

    def clear(self):
        self.terms.clear()
        self.tagger.clear()

    def parse(self):
        if not self.tagger.parse():
            return self.terms

        for n in range(self.tagger.nbest()):
            if not self.tagger.next():
                break
            termlist = []
            for i in range(self.tagger.size()):
                term = AbbrChar(self.tagger.x(i, 0), self.tagger.x(i, 2))
                term.set_tone(self.tagger.x(i, 1))
                term.set_wheater(self.tagger.yname(self.tagger.y(i)))
                termlist.append(term)
            self.terms.append(termlist)

        return self.terms


def parse_abbrs(company_name, model_file_path=None, nbest=None):
    fullname = set_full_name(company_name)
    if not model_file_path:
        model_file_path = get_closest_file(config.ABBR_TRAIN_MODEL_PATH, '_crf_abbr_keep_model')
    parse_instance = RegCom(model_file_path, nbest)

    parse_instance.addterms(fullname)

    rich_termlist = parse_instance.parse()

    abbrlist = []
    for termlist in rich_termlist:
        sb = ''
        for term in termlist:
            if term.wheater == 'K':
                sb = ''.join([sb, term.word])
        if sb.strip() and sb not in abbrlist and len(sb) > 1:
                abbrlist.append(sb)

    ltc_abb_list = load_ltd_cp_abbr(company_name)

    if len(abbrlist) < 2:
        for abbr in ltc_abb_list:
            if abbr not in abbrlist:
                abbrlist.append(abbr)
    else:
        redup_ltc_abb_list = []
        for abbr in ltc_abb_list:
            if abbr not in abbrlist:
                redup_ltc_abb_list.append(abbr)
        abbrlist[2:2] = redup_ltc_abb_list

    parse_instance.clear()

    return limit_abbrlist(company_name, abbrlist)


# 限定简称中不能有全称，最多返回5个简称
def limit_abbrlist(company_name, abbrlist):
    ret_list = []
    for abbr in abbrlist:
        if abbr != company_name and abbr not in ret_list:
            ret_list.append(abbr)
        if len(ret_list) == 5:
            break
    return ret_list


def demo_convert_pinyinlist(name):
    if not isJVMStarted():
        HanlpJvm()

    tokenizer = JClass('com.hankcs.hanlp.HanLP')
    pinyinlist = tokenizer.convertToPinyinList(name)
    return pinyinlist


def set_full_name(name):
    cp_name = name
    replace_chars = ['（', '）', '(', ')', '\n', ' ']
    for char in replace_chars:
        cp_name = cp_name.replace(char, '')
    terms_list = []
    pinyinlist = demo_convert_pinyinlist(cp_name)
    if config.CLASSSIFY_MODEL_FILE:
        name_term = get_model_abbr(cp_name)
        for word_term in name_term.words_term:
            i = 0
            for char in word_term.word:
                terms_list.append(AbbrChar(char, word_term.type + str(i)))
                i += 1
    else:
        with NLPDriver('http://h133:5007/api/abbner', 5000) as driver:
            seg = driver.segment(cp_name.encode('UTF-8'))
            for term in seg:
                i = 0
                for word in term['word']:
                    terms_list.append(AbbrChar(word, term['type'] + str(i)))
                    i += 1
    j = 0
    try:
        for pinyin in pinyinlist:
            tone = pinyin.getTone()
            terms_list[j].set_tone(tone)
            j += 1
    except IndexError as ex:
        print(ex)
    return terms_list


def write_back_result(termlist, outputfile):
    abb_results = {}

    for term in termlist:
        abb_results.update({term['full_name']: term['abbs']})

    with open(outputfile, 'w') as f:
        for (k, v) in abb_results.items():
            lists = [k+'\t'+line + '\n' for line in v]
            # lists = [k+'\t'+str(v) + '\n' ]
            f.writelines(lists)
    f.close()

    return abb_results


def load_ltd_cp_abbr(company_name):
    fullname = set_full_name(company_name)
    rm_instance = RecCom('/home/hadoop/wnd/usr/crf_cp_name_easy/171213_first_model/new_abbr_feature.crfpp', 3)
    rm_instance.addterms(fullname)
    rich_termlist = rm_instance.parse()
    abbrlist = []
    for termlist in rich_termlist:
        sb = ''
        for term in termlist:
            if term.wheater == 'K':
                sb = ''.join([sb, term.char])
        if sb.strip() and sb not in abbrlist and len(sb) > 1:
            abbrlist.append(sb)
    return abbrlist


def load_model(arg, model_file_path=None, output_file_path=None):
    if isinstance(arg, list):
        params = arg[:len(arg) - 1]
        arg = arg[-1]
    else:
        params = None

    termlist = []
    if os.path.exists(arg):
        with open(arg, 'r') as fp:
            lines = fp.readlines()
            for line in lines:
                name = line.strip()
                term = parse_abbrs(line, model_file_path, 5)
                abbr_tuple = {'full_name': name, 'abbs': term}
                termlist.append(abbr_tuple)
                print(name)
    else:
        print(arg)
        term = parse_abbrs(arg, model_file_path, 5)
        abbr_tuple = {'full_name': arg, 'abbs': term}
        termlist.append(abbr_tuple)

    if not output_file_path:
        tmp_outfile = tempfile.mkstemp()
        output_file_path = tmp_outfile[1]
        print('输出路径为%s', output_file_path)

    abbrs_results = write_back_result(termlist, output_file_path)

    return output_file_path, abbrs_results

if __name__ == '__main__':
    options = ['-n', '2', '-v', '0', '/mnt/vol_0/wnd/usr/cmb_in/generate_stage/pretreatment/180521/1526890887_test_name']
    load_model(options)
