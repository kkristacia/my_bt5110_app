from django.shortcuts import render
from django.db import connections
from django.shortcuts import redirect
from django.http import Http404
from django.db.utils import IntegrityError

from plotly.offline import plot
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.utils import namedtuplefetchall, clamp
from app.forms import ImoForm

import numpy as np
from sklearn.linear_model import LinearRegression

PAGE_SIZE = 20
COLUMNS = [
    'imo',
    'ship_name',
    'technical_efficiency_number',
    'ship_type',
    'issue',
    'expiry',
]

COLUMNS2 = [
    'count',
    'ship_type',
    'min',
    'avg',
    'max',
]

COLUMNS3 = [
    'ship_id',
    'verifier_id',
    'date_id',
    'eedi',
    'port_regist',
    'total_fuel_consmp',
    'total_co2',
    'total_time_sea',
    'co2_emm_per_dist',
    'co2_emm_per_tw',
]

COLUMNS4 = [
    'ship_id',
    'imo',
    'ship_name',
    'ship_type',   
]

COLUMNS5 = [
    'verifier_id',
    'verifier_name',
    'nab_company',
    'verifier_address',
    'verifier_city',
    'accredition_no',
    'verifier_country'
]

COLUMNS6= [
    'date_id',
    'date',
    'week',
    'month',
    'quarter',
    'year_half',
    'year'
]


def index(request):
    """Shows the main page"""
    context = {'nbar': 'home'}
    return render(request, 'index.html', context)


def db(request):
    """Shows very simple DB page"""
    with connections['default'].cursor() as cursor:
        cursor.execute('INSERT INTO app_greeting ("when") VALUES (NOW());')
        cursor.execute('SELECT "when" FROM app_greeting;')
        greetings = namedtuplefetchall(cursor)

    context = {'greetings': greetings, 'nbar': 'db'}
    return render(request, 'db.html', context)

def aggregation(request, page=1):
    """Shows the emissions table page"""
    msg = None
    order_by = request.GET.get('order_by', '')
    order_by = order_by if order_by in COLUMNS else 'imo'

    with connections['default'].cursor() as cursor:
        cursor.execute('select count(distinct c.imo), c.ship_type, min(c.technical_efficiency_number), avg(c.technical_efficiency_number), max(c.technical_efficiency_number) from co2emission_reduced as c group by c.ship_type;')
        count = cursor.fetchone()[0]
        num_pages = (count - 1) // PAGE_SIZE + 1
        page = clamp(page, 1, num_pages)

        offset = (page - 1) * PAGE_SIZE
        cursor.execute(f'''
            SELECT {"count(distinct c.imo), c.ship_type, min(c.technical_efficiency_number), avg(c.technical_efficiency_number), max(c.technical_efficiency_number)"}
	    FROM co2emission_reduced as c
            GROUP BY c.ship_type
            OFFSET %s
            LIMIT %s
        ''', [offset, PAGE_SIZE])
        rows = namedtuplefetchall(cursor)

    imo_deleted = request.GET.get('deleted', False)
    if imo_deleted:
        msg = f'✔ IMO {imo_deleted} deleted'

    context = {
        'nbar': 'aggregation',
        'page': page,
        'rows': rows,
        'num_pages': num_pages,
        'msg': msg,
        'order_by': order_by
    }
    return render(request, 'aggregation.html', context)


def emissions(request, page=1):
    """Shows the emissions table page"""
    msg = None
    order_by = request.GET.get('order_by', '')
    order_by = order_by if order_by in COLUMNS else 'imo'

    with connections['default'].cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM co2emission_reduced')
        count = cursor.fetchone()[0]
        num_pages = (count - 1) // PAGE_SIZE + 1
        page = clamp(page, 1, num_pages)

        offset = (page - 1) * PAGE_SIZE
        cursor.execute(f'''
            SELECT {", ".join(COLUMNS)}
            FROM co2emission_reduced
            ORDER BY {order_by}
            OFFSET %s
            LIMIT %s
        ''', [offset, PAGE_SIZE])
        rows = namedtuplefetchall(cursor)

    imo_deleted = request.GET.get('deleted', False)
    if imo_deleted:
        msg = f'✔ IMO {imo_deleted} deleted'

    context = {
        'nbar': 'emissions',
        'page': page,
        'rows': rows,
        'num_pages': num_pages,
        'msg': msg,
        'order_by': order_by
    }
    return render(request, 'emissions.html', context)


def insert_update_values(form, post, action, imo):
    """
    Inserts or updates database based on values in form and action to take,
    and returns a tuple of whether action succeded and a message.
    """
    if not form.is_valid():
        return False, 'There were errors in your form'

    # Set values to None if left blank
    cols = COLUMNS[:]
    values = [post.get(col, None) for col in cols]
    values = [val if val != '' else None for val in values]

    if action == 'update':
        # Remove imo from updated fields
        cols, values = cols[1:], values[1:]
        with connections['default'].cursor() as cursor:
            cursor.execute(f'''
                UPDATE co2emission_reduced
                SET {", ".join(f"{col} = %s" for col in cols)}
                WHERE imo = %s;
            ''', [*values, imo])
        return True, '✔ IMO updated successfully'

    # Else insert
    with connections['default'].cursor() as cursor:
        cursor.execute(f'''
            INSERT INTO co2emission_reduced ({", ".join(cols)})
            VALUES ({", ".join(["%s"] * len(cols))});
        ''', values)
    return True, '✔ IMO inserted successfully'


def emission_detail(request, imo=None):
    """Shows the form where the user can insert or update an IMO"""
    success, form, msg, initial_values = False, None, None, {}
    is_update = imo is not None

    if is_update and request.GET.get('inserted', False):
        success, msg = True, f'✔ IMO {imo} inserted'

    if request.method == 'POST':
        # Since we set imo=disabled for updating, the value is not in the POST
        # data so we need to set it manually. Otherwise if we are doing an
        # insert, it will be None but filled out in the form
        if imo:
            request.POST._mutable = True
            request.POST['imo'] = imo
        else:
            imo = request.POST['imo']

        form = ImoForm(request.POST)
        action = request.POST.get('action', None)

        if action == 'delete':
            with connections['default'].cursor() as cursor:
                cursor.execute('DELETE FROM co2emission_reduced WHERE imo = %s;', [imo])
            return redirect(f'/emissions?deleted={imo}')
        try:
            success, msg = insert_update_values(form, request.POST, action, imo)
            if success and action == 'insert':
                return redirect(f'/emissions/imo/{imo}?inserted=true')
        except IntegrityError:
            success, msg = False, 'IMO already exists'
        except Exception as e:
            success, msg = False, f'Some unhandled error occured: {e}'
    elif imo:  # GET request and imo is set
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT * FROM co2emission_reduced WHERE imo = %s', [imo])
            try:
                initial_values = namedtuplefetchall(cursor)[0]._asdict()
            except IndexError:
                raise Http404(f'IMO {imo} not found')

    # Set dates (if present) to iso format, necessary for form
    # We don't use this in class, but you will need it for your project
    for field in ['doc_issue_date', 'doc_expiry_date']:
        if initial_values.get(field, None) is not None:
            initial_values[field] = initial_values[field].isoformat()

    # Initialize form if not done already
    form = form or ImoForm(initial=initial_values)
    if is_update:
        form['imo'].disabled = True

    context = {
        'nbar': 'emissions',
        'is_update': is_update,
        'imo': imo,
        'form': form,
        'msg': msg,
        'success': success
    }
    return render(request, 'emission_detail.html', context)


def visual(request):
    """ 
    View demonstrating how to display a graph object
    on a web page with Plotly. 
    """
    
    #cursor = conn.cursor()    
 
    with connections['default'].cursor() as cursor:
        cursor.execute('select count(distinct c.imo), c.ship_type, min(c.technical_efficiency_number), avg(c.technical_efficiency_number), max(c.technical_efficiency_number) from co2emission_reduced as c group by c.ship_type;')
        rows = cursor.fetchall() #if this is here, indented, then its fine

    #print(str(rows))
    # Generating some data for plots.
    li_avg=[]
    li_x=[]
    li_name=[]
    li_max=[]
    for i in range(len(rows)):
        #print(rows[i][3])
        li_avg.append(rows[i][3])
        li_x.append(i)
        li_name.append(rows[i][1])
        li_max.append(rows[i][4])

    # List of graph objects for figure.
    # Each object will contain on series of data.
    graphs = []
    
    fig1 = go.Bar(x=li_name,y=li_avg) 

    fig2 = go.Pie(labels=li_name,values=li_max) 
	
    # Adding linear plot of y1 vs. x.
    #graphs.append(
    #	fig
    #)


    # Setting layout of the figure.
    layout = {
        'title': 'Barchart of each ship type avg EEDI',
        'xaxis_title': 'Ship type',
        'yaxis_title': 'avg EEDI',
        'height': 620,
        'width': 560,
    }
    layout2 = {
        'title': 'Pie chart of each ship type max EEDI',
        'xaxis_title': 'Ship type',
        'yaxis_title': 'avg EEDI',
        'height': 620,
        'width': 560,
    }

    # Getting HTML needed to render the plot.
    plot_div = plot({'data': fig1, 'layout': layout}, 
                    output_type='div')
    plot_div2 = plot({'data': fig2, 'layout': layout2}, 
                    output_type='div')

    #new part for the group project***********************************************
    with connections['default'].cursor() as cursor:
        cursor.execute('select f.total_co2, f.total_time_sea, f.total_fuel_consmp from fact as f;')
        rows2 = cursor.fetchall() #if this is here, indented, then its fine

    co2_li=[]
    tts_li=[]
    tfc_li=[]
    for i in range(len(rows2)):
        co2_li.append(rows2[i][0])    
        tts_li.append(rows2[i][1]) 
        tfc_li.append(rows2[i][2])

    fig3 = go.Scatter(x=np.log10(tts_li),y=np.log10(co2_li), mode='markers',name='log10 total co2') 
    fig4 = go.Scatter(x=np.log10(tts_li),y=np.log10(tfc_li), mode='markers',name='log10 total time at sea') 
    
    lr=LinearRegression().fit(np.log10(tts_li).reshape(-1,1),np.log10(co2_li).reshape(-1,1))
    lr_y_pred = lr.predict(np.log10(tts_li).reshape(-1,1))  
    lr_y_pred_li=[]
    for i in range(len(lr_y_pred)):
        lr_y_pred_li.append(lr_y_pred[i][0])

    fig3_lr= go.Scatter(x=np.log10(tts_li),y=lr_y_pred_li,line=dict(color='firebrick', width=4), name='linear regression')  

    lr2=LinearRegression().fit(np.log10(tts_li).reshape(-1,1),np.log10(tfc_li).reshape(-1,1))
    lr2_y_pred = lr2.predict(np.log10(tts_li).reshape(-1,1))  
    lr2_y_pred_li=[]
    for i in range(len(lr2_y_pred)):
        lr2_y_pred_li.append(lr2_y_pred[i][0])
    fig4_lr= go.Scatter(x=np.log10(tts_li),y=lr2_y_pred_li,line=dict(color='firebrick', width=4),name='linear regression')  

    layout3 = {
        'title': 'Log_10(Total time at sea) versus Log_10(Total Co2)',
        #'title': str(lr2_y_pred_li),
        'yaxis_title': 'Log_10(Total Co2)',
        'xaxis_title': 'Log_10(Total time at sea)',
        'height': 620,
        'width': 560,
    }
    layout4 = {
        'title': 'Log_10(Total time at sea) versus Log_10(Total Fuel Consumption)',
        'yaxis_title': 'Log_10(Total Fuel Consumption)',
        'xaxis_title': 'Log_10(Total time at sea)',
        'height': 620,
        'width': 560,
    }
    plot_div3 = plot({'data':[fig3, fig3_lr], 'layout': layout3}, 
                    output_type='div')
    plot_div4 = plot({'data': [fig4, fig4_lr], 'layout': layout4}, 
                    output_type='div')

    with connections['default'].cursor() as cursor:
        cursor.execute('select avg(f.total_co2), avg(f.total_time_sea), s.ship_type from fact as f, ship_dim as s where f.ship_id = s.ship_id group by s.ship_type;')
        rows3 = cursor.fetchall() #if this is here, indented, then its fine
    
    avg_co2_li=[]
    avg_tts_li=[]
    ship_type_li=[]
    for i in range(len(rows3)):
        avg_co2_li.append(rows3[i][0])    
        avg_tts_li.append(rows3[i][1]) 
        ship_type_li.append(rows3[i][2])

    fig5 = go.Bar(x=ship_type_li,y=avg_co2_li) 
    fig6 = go.Pie(labels=ship_type_li,values=avg_tts_li) 

    layout5 = {
        'title': 'average total co2 bar chart by ship type',
        'yaxis_title': 'average total co2',
        'xaxis_title': 'ship type',
        'height': 620,
        'width': 560,
    }
    layout6 = {
        'title': 'average total fuel consumption pie chart by ship type',
        'yaxis_title': 'Total Fuel Consumption)',
        'xaxis_title': 'Total time at sea',
        'height': 620,
        'width': 560,
    }
    plot_div5 = plot({'data': fig5, 'layout': layout5}, 
                    output_type='div')
    plot_div6 = plot({'data': fig6, 'layout': layout6}, 
                    output_type='div')
    return render(request, 'visual.html', 
                  context={'plot_div': plot_div,'plot_div2':plot_div2,'plot_div3':plot_div3, 'plot_div4':plot_div4, 'plot_div5':plot_div5, 'plot_div6':plot_div6, 'nbar': 'visual'})



def fact(request, page=1):
    """Shows the fact table page"""
    msg = None
    order_by = request.GET.get('order_by', '')
    order_by = order_by if order_by in COLUMNS3 else 'ship_id'

    with connections['default'].cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM fact')
        count = cursor.fetchone()[0]
        num_pages = (count - 1) // PAGE_SIZE + 1
        page = clamp(page, 1, num_pages)

        offset = (page - 1) * PAGE_SIZE
        cursor.execute(f'''
            SELECT {", ".join(COLUMNS3)}
            FROM fact
	    ORDER BY {order_by}
            OFFSET %s
            LIMIT %s
        ''', [offset, PAGE_SIZE])
        rows = namedtuplefetchall(cursor)

    imo_deleted = request.GET.get('deleted', False)
    if imo_deleted:
        msg = f'✔ IMO {imo_deleted} deleted'

    context = {
        'nbar': 'fact',
        'page': page,
        'rows': rows,
        'num_pages': num_pages,
        'msg': msg,
        'order_by': order_by
    }
    return render(request, 'fact.html', context)



def ship_dim(request, page=1):
    """Shows the ship_dim table page"""
    msg = None
    order_by = request.GET.get('order_by', '')
    order_by = order_by if order_by in COLUMNS4 else 'ship_id'

    with connections['default'].cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM ship_dim')
        count = cursor.fetchone()[0]
        num_pages = (count - 1) // PAGE_SIZE + 1
        page = clamp(page, 1, num_pages)

        offset = (page - 1) * PAGE_SIZE
        cursor.execute(f'''
            SELECT {", ".join(COLUMNS4)}
            FROM ship_dim
	    ORDER BY {order_by}
            OFFSET %s
            LIMIT %s
        ''', [offset, PAGE_SIZE])
        rows = namedtuplefetchall(cursor)

    imo_deleted = request.GET.get('deleted', False)
    if imo_deleted:
        msg = f'✔ IMO {imo_deleted} deleted'

    context = {
        'nbar': 'ship_dim',
        'page': page,
        'rows': rows,
        'num_pages': num_pages,
        'msg': msg,
	'order_by': order_by
    }
    return render(request, 'ship_dim.html', context)



def adv_q_visual(request):
    """ 
    View demonstrating how to display a graph object
    on a web page with Plotly. 
    """
    
    #cursor = conn.cursor()    
 
    with connections['default'].cursor() as cursor:
        cursor.execute('SELECT d.Year, s.ship_type,ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY f.eedi ASC)::NUMERIC, 2) AS percentile_25, ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY f.eedi ASC)::NUMERIC, 2) AS percentile_50, ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY f.eedi ASC)::NUMERIC, 2) AS percentile_75, ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY f.eedi ASC)::NUMERIC, 2) AS percentile_95 FROM fact f, ship_dim s, date_dim d WHERE f.ship_id= s.ship_id AND d.date_id = f.date_id GROUP BY ROLLUP(d.Year, s.ship_type);')
        rows = cursor.fetchall() #if this is here, indented, then its fine

    #print(str(rows))
    # Generating some data for plots.
    year_li=[2019,2020,2021]
    eedi_agg_25pc_li=[]
    eedi_agg_50pc_li=[]
    eedi_agg_75pc_li=[]
    eedi_agg_95pc_li=[]

    eedi_agg_25pc_li.append(rows[8][2])
    eedi_agg_25pc_li.append(rows[17][2])
    eedi_agg_25pc_li.append(rows[27][2])

    eedi_agg_50pc_li.append(rows[8][3])
    eedi_agg_50pc_li.append(rows[17][3])
    eedi_agg_50pc_li.append(rows[27][3])

    eedi_agg_75pc_li.append(rows[8][4])
    eedi_agg_75pc_li.append(rows[17][4])
    eedi_agg_75pc_li.append(rows[27][4])

    eedi_agg_95pc_li.append(rows[8][5])
    eedi_agg_95pc_li.append(rows[17][5])
    eedi_agg_95pc_li.append(rows[27][5])
 
    fig1a = go.Scatter(x=year_li,y=eedi_agg_25pc_li,name='25th percentile') 
    fig1b = go.Scatter(x=year_li,y=eedi_agg_50pc_li,name='50th percentile') 
    fig1c = go.Scatter(x=year_li,y=eedi_agg_75pc_li,name='75th percentile') 
    fig1d = go.Scatter(x=year_li,y=eedi_agg_95pc_li) 

    # Setting layout of the figure.
    layout = {
        'title':  'aggregated ship type 25th-75th percentile eedi versus year' ,
        'xaxis_title': 'year',
        'yaxis_title': 'EEDI',
        'height': 620,
        'width': 560,
    }

    layout_E = {
        'title':  'aggregated ship type 95th percentile eedi versus year' ,
        'xaxis_title': 'year',
        'yaxis_title': 'EEDI',
        'height': 620,
        'width': 560,
    }


    # Getting HTML needed to render the plot.
    plot_div = plot({'data': [fig1a,fig1b,fig1c], 'layout': layout}, 
                    output_type='div')
    plot_div_E = plot({'data': [fig1d], 'layout': layout_E}, 
                    output_type='div')

#************** second advanced query visualization ************************
    with connections['default'].cursor() as cursor:
        cursor.execute('SELECT rank_filter.* FROM (SELECT s.ship_name, s.ship_type, f.eedi,RANK() OVER (PARTITION BY s.ship_type ORDER BY f.eedi) FROM fact f, ship_dim s, date_dim d WHERE f.ship_id= s.ship_id AND d.date_id = f.date_id AND d.Year = 2021 ) rank_filter WHERE RANK <=3;')
        rows2 = cursor.fetchall() #if this is here, indented, then its fine
    
    name_li=[]
    eedi_li=[]
    type_li=[]

    for i in range(len(rows2)):
        name_li.append(rows2[i][0])
        eedi_li.append(rows2[i][2])    
        type_li.append(rows2[i][1])

    fig2a=go.Bar(x=name_li[0:3],y=eedi_li[0:3],name=type_li[0])  
    fig2b=go.Bar(x=name_li[3:6],y=eedi_li[3:6],name=type_li[4]) 
    fig2c=go.Bar(x=[name_li[6]],y=[eedi_li[6]],name=type_li[6]) 
    fig2d=go.Bar(x=name_li[7:10],y=eedi_li[7:10],name=type_li[8]) 
    fig2e=go.Bar(x=name_li[10:13],y=eedi_li[10:13],name=type_li[10]) 
    fig2f=go.Bar(x=name_li[13:16],y=eedi_li[13:16],name=type_li[13]) 
    fig2g=go.Bar(x=name_li[16:19],y=eedi_li[16:19],name=type_li[16]) 
    fig2h=go.Bar(x=name_li[19:21],y=eedi_li[19:21],name=type_li[19]) 
    fig2i=go.Bar(x=[name_li[21]],y=[eedi_li[21]],name=type_li[21]) 

    layout2 = {
        'title': 'top 3 lowest eedi ships from each ship category'  ,
        'xaxis_title': 'ship name',
        'yaxis_title': 'EEDI',
        'height': 620,
        'width': 700,
    }  
    plot_div2=plot({'data': [fig2a,fig2b,fig2c,fig2d,fig2e,fig2f,fig2g,fig2h,fig2i], 'layout': layout2}, 
                    output_type='div')

#********************** do the third advanced query here
    with connections['default'].cursor() as cursor:
        cursor.execute('SELECT rank_filter.* FROM ( SELECT s.ship_name, s.ship_type, sum_f.avg_ship, sum_f.avg_time, RANK() OVER ship_time AS time_rank, ROUND(AVG(sum_f.avg_ship) OVER ship_eedi::NUMERIC, 2) AS avg_type FROM ship_dim s, (SELECT f1.ship_id, ROUND(AVG(f1.total_time_sea)::NUMERIC, 2) AS avg_time, ROUND(AVG(f1.eedi)::NUMERIC, 2) AS avg_ship FROM fact f1 GROUP BY f1.ship_id) sum_f WHERE sum_f.ship_id= s.ship_id WINDOW ship_time AS (PARTITION BY  s.ship_type ORDER BY (sum_f.avg_time) DESC), ship_eedi AS (PARTITION BY  s.ship_type ORDER BY (sum_f.avg_ship) ASC ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) ORDER BY s.ship_type) rank_filter WHERE time_rank<=3;')
        rows3 = cursor.fetchall() #if this is here, indented, then its fine
    
    name_li2=[]
    eedi_li2=[]
    type_li2=[]

    for i in range(len(rows3)):
        name_li2.append(rows3[i][0])
        eedi_li2.append(rows3[i][2])    
        type_li2.append(rows3[i][1])

    fig3a=go.Bar(x=name_li2[0:3],y=eedi_li2[0:3],name=type_li2[0])  
    fig3b=go.Bar(x=name_li2[3:6],y=eedi_li2[3:6],name=type_li2[4]) 
    fig3c=go.Bar(x=[name_li2[6]],y=[eedi_li2[6]],name=type_li2[6]) 
    fig3d=go.Bar(x=name_li2[7:10],y=eedi_li2[7:10],name=type_li2[8]) 
    fig3e=go.Bar(x=name_li2[10:13],y=eedi_li2[10:13],name=type_li2[10]) 
    fig3f=go.Bar(x=name_li2[13:16],y=eedi_li2[13:16],name=type_li2[13]) 
    fig3g=go.Bar(x=name_li2[16:19],y=eedi_li2[16:19],name=type_li2[16]) 
    fig3h=go.Bar(x=name_li2[19:21],y=eedi_li2[19:21],name=type_li2[19]) 
    fig3i=go.Bar(x=[name_li2[21]],y=[eedi_li2[21]],name=type_li2[21]) 
    fig3j=go.Bar(x=[name_li2[22]],y=[eedi_li2[22]],name=type_li2[22]) 

    layout3 = {
        'title': 'top 3 highest eedi ships from each ship category'  ,
        'xaxis_title': 'ship name',
        'yaxis_title': 'EEDI',
        'height': 620,
        'width': 700,
    }  
    plot_div3=plot({'data': [fig3a,fig3b,fig3c,fig3d,fig3e,fig3f,fig3g,fig3h,fig3i,fig3j], 'layout': layout3}, 
                    output_type='div')   

   
    return render(request, 'adv_q_visual.html', 
                  context={'plot_div': plot_div,'plot_div_E': plot_div_E, 'plot_div2': plot_div2,'plot_div3': plot_div3,'nbar': 'adv_q_visual'})




def verifier_dim(request, page=1):
    """Shows the verifier_dim table page"""
    msg = None
    order_by = request.GET.get('order_by', '')
    order_by = order_by if order_by in COLUMNS5 else 'verifier_id'

    with connections['default'].cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM verifier_dim')
        count = cursor.fetchone()[0]
        num_pages = (count - 1) // PAGE_SIZE + 1
        page = clamp(page, 1, num_pages)

        offset = (page - 1) * PAGE_SIZE
        cursor.execute(f'''
            SELECT {", ".join(COLUMNS5)}
            FROM verifier_dim
	    ORDER BY {order_by}
            OFFSET %s
            LIMIT %s
        ''', [offset, PAGE_SIZE])
        rows = namedtuplefetchall(cursor)

    imo_deleted = request.GET.get('deleted', False)
    if imo_deleted:
        msg = f'✔ IMO {imo_deleted} deleted'

    context = {
        'nbar': 'verifier_dim',
        'page': page,
        'rows': rows,
        'num_pages': num_pages,
        'msg': msg,
        'order_by': order_by
    }
    return render(request, 'verifier_dim.html', context)


def date_dim(request, page=1):
    """Shows the date_dim table page"""
    msg = None
    order_by = request.GET.get('order_by', '')
    order_by = order_by if order_by in COLUMNS6 else 'date_id'

    with connections['default'].cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM verifier_dim')
        count = cursor.fetchone()[0]
        num_pages = (count - 1) // PAGE_SIZE + 1
        page = clamp(page, 1, num_pages)

        offset = (page - 1) * PAGE_SIZE
        cursor.execute(f'''
            SELECT {", ".join(COLUMNS6)}
            FROM date_dim
	    ORDER BY {order_by}
            OFFSET %s
            LIMIT %s
        ''', [offset, PAGE_SIZE])
        rows = namedtuplefetchall(cursor)

    imo_deleted = request.GET.get('deleted', False)
    if imo_deleted:
        msg = f'✔ IMO {imo_deleted} deleted'

    context = {
        'nbar': 'date_dim',
        'page': page,
        'rows': rows,
        'num_pages': num_pages,
        'msg': msg,
        'order_by': order_by
    }
    return render(request, 'date_dim.html', context)