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

PAGE_SIZE = 20
COLUMNS = [
    'imo',
    'ship_name',
    'technical_efficiency_number',
    'ship_type',
    'issue',
    'expiry'
]

COLUMNS2 = [
    'count',
    'ship_type',
    'min',
    'avg',
    'max'
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

    return render(request, 'visual.html', 
                  context={'plot_div': plot_div,'plot_div2':plot_div2,'nbar': 'visual'})

def fact(request, page=1):
    """Shows the fact table page"""
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
    return render(request, 'fact.html', context)


