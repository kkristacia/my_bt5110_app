from django.urls import path
from django.contrib import admin
#from mysite.core import views

import app.views

admin.autodiscover()



urlpatterns = [
    path('', app.views.index, name='index'),
    path('db/', app.views.db, name='db'),
    path('emissions/', app.views.emissions, name='emissions'),
    path('emissions/<int:page>', app.views.emissions, name='emissions'),
    path('emissions/imo/', app.views.emission_detail, name='emission_detail'),
    path('emissions/imo/<int:imo>', app.views.emission_detail, name='emission_detail'),
    path('admin/', admin.site.urls),
    path('aggregation/', app.views.aggregation, name='aggregation'), 
    path('visual/', app.views.visual, name='visual'), 
    path('adv_q_visual/', app.views.adv_q_visual, name='adv_q_visual'), 
    path('fact/', app.views.fact, name='fact'),
    path('fact/<int:page>', app.views.fact, name='fact'),
    path('ship_dim/', app.views.ship_dim, name='ship_dim'),
    path('ship_dim/<int:page>', app.views.ship_dim, name='ship_dim'),
    path('verifier_dim/', app.views.verifier_dim, name='verifier_dim'),
    path('verifier_dim/<int:page>', app.views.verifier_dim, name='verifier_dim'),
    path('date_dim/', app.views.date_dim, name='date_dim'),
    path('date_dim/<int:page>', app.views.date_dim, name='date_dim'),
]


