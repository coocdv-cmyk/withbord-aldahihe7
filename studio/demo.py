import uuid

def project(name='yusuf'):
    if name=='business':
        items=[
            ('خطوة صغيرة تصنع فرقًا','الادخار يبدأ بتخصيص جزء من الدخل وتحديد هدف واضح.',['story-business']),
            ('فهم الأفكار قبل القرار','التفكير الهادئ يساعدنا على مراجعة خياراتنا.',['story-mind']),
            ('المعرفة عادة مستمرة','القراءة والتعلم يفتحان لنا فرصًا جديدة.',['story-learning'])]
        title='عينة المال والتطوير';domain='finance'
    else:
        items=[
            ('القميص والانتظار','الذي في يد ذلك الرجل قميص. وهو ثالث قميص في هذه الحكاية.',['story-elder','story-shirt']),
            ('في قاع البئر','صبي في الظلام. وفوقه دائرة صغيرة من السماء.',['story-well','story-boy']),
            ('قافلة تعبر الطريق','وفي الصباح مرت قافلة. نزل الدلو ليأتي بماء فصعد بصبي.',['story-caravan']),
            ('حكاية تربطها القمصان','ثلاثة قمصان وحلم واحد صدق.',['story-shirt-marked','story-shirt-torn','story-shirt'])]
        title='يوسف — اختبار لغة الوايت بورد';domain='religion'
    scenes=[{'title':t,'text':text,'assets':assets,'duration':8.,'layout':'focus'} for t,text,assets in items]
    if name!='business':
        scenes[0]['labels']={'0':'يعقوب'};scenes[1]['labels']={'1':'يوسف'}
        scenes[3]['labels']={'0':'قميص الدم','1':'القميص الممزق','2':'قميص البشارة'};scenes[3]['layout']='compare'
    return {'version':2,'id':uuid.uuid4().hex,'title':title,'domain':domain,'script':'\n'.join(s['text'] for s in scenes),
            'duration':len(scenes)*8.,'planner':'rules','renderer':'whiteboard','resolution':'1080p',
            'accent':'#315d50','hand':True,'camera':True,'paper':'cream','scenes':scenes,
            'notes':'عينة بصرية قصيرة، وليست إنتاج قصة يوسف بالكامل أو توثيقًا للنص.'}
