from collections import defaultdict
from couchdbkit import ResourceNotFound
from bihar.reports.indicators.filters import A_MONTH, is_pregnant_mother, get_add, get_edd
from couchforms.safe_index import safe_index
from dimagi.utils.parsing import string_to_datetime
import datetime as dt
from bihar.reports.indicators.visits import visit_is, get_related_prop

EMPTY = (0,0)
GRACE_PERIOD = dt.timedelta(days=7)


def _num_denom(num, denom):
    return "%s/%s" % (num, denom)

def _in_last_month(date):
    today = dt.datetime.today().date()
    return today - A_MONTH < date < today

def _in_timeframe(date, days):
    today = dt.datetime.today().date()
    return today - dt.timedelta(days=days) < date < today

def _mother_due_in_window(case, days):
    get_visitduedate = lambda case: case.edd - dt.timedelta(days=days) + GRACE_PERIOD
    return is_pregnant_mother(case) and get_edd(case) and _in_last_month(get_visitduedate(case))
        
def _mother_delivered_in_window(case, days):
    get_visitduedate = lambda case: case.add + dt.timedelta(days=days) + GRACE_PERIOD
    return is_pregnant_mother(case) and get_add(case) and _in_last_month(get_visitduedate(case))

def _num_denom_count(cases, num_func, denom_func):
    num = denom = 0
    for case in cases:
        denom_diff = denom_func(case)
        if denom_diff:
            denom += denom_diff
            num_diff = num_func(case)
            assert num_diff <= denom_diff
            # this is to prevent the numerator from ever passing the denominator
            # though is probably not totally accurate
            num += num_diff
    return _num_denom(num, denom)

def _visits_due(case, schedule):
    return [i + 1 for i, days in enumerate(schedule) \
            if _mother_delivered_in_window(case, days)]

def _visits_done(case, schedule, type):
    due = _visits_due(case, schedule)
    count = len(filter(lambda a: visit_is(a, type), case.actions))
    return len([v for v in due if count > v])

def _delivered_in_timeframe(case, days):
    return is_pregnant_mother(case) and get_add(case) and _in_timeframe(case.add, days)

def _delivered_at_in_timeframe(case, at, days):
    at = at if isinstance(at, list) else [at]
    return getattr(case, 'birth_place', None) in at and _delivered_in_timeframe(case, days)

def _get_time_of_visit_after_birth(case):
    for action in case.actions:
        if action.updated_unknown_properties.get("add", None):
            return action.date
    return None

def _visited_in_timeframe_of_birth(case, days):
    visit_time = _get_time_of_visit_after_birth(case)
    time_birth = get_related_prop(case, "time_of_birth") or get_add(case) # use add if time_of_birth can't be found
    if visit_time and time_birth:
        if isinstance(time_birth, dt.date):
            time_birth = dt.datetime.combine(time_birth, dt.datetime.time(dt.datetime.now())) #convert date to dt.datetime
        return time_birth < visit_time < time_birth + dt.timedelta(days=days)
    return False

def _weak_babies(case): # :(
    return is_pregnant_mother(case) and\
           (getattr(case, 'recently_delivered', None) == "yes" or get_related_prop(case, 'birth_status') == "live_birth")


    
# NOTE: cases in, values out might not be the right API
# but it's what we need for the first set of stuff.
# might want to revisit.

# NOTE: this is going to be slooooow
def bp2_last_month(cases):
    due = lambda case: 1 if _mother_due_in_window(case, 75) else 0
    # make sure they've done 2 bp visits
    done = lambda case: 1 if len(filter(lambda a: visit_is(a, 'bp'), case.actions)) >= 2 else 0
    return _num_denom_count(cases, due, done)    
    
def bp3_last_month(cases):
    due = lambda case: 1 if _mother_due_in_window(case, 45) else 0
    # make sure they've done 2 bp visits
    done = lambda case: 1 if len(filter(lambda a: visit_is(a, 'bp'), case.actions)) >= 3 else 0
    return _num_denom_count(cases, due, done)    
    
def pnc_last_month(cases):
    pnc_schedule = (1, 3, 6)
    due = lambda case: len(_visits_due(case, pnc_schedule))
    done = lambda case: _visits_done(case, pnc_schedule, "pnc")
    return _num_denom_count(cases, done, due)

def eb_last_month(cases):
    eb_schedule = (14, 28, 60, 90, 120, 150)
    due = lambda case: len(_visits_due(case, eb_schedule))
    done = lambda case: _visits_done(case, eb_schedule, "eb")
    return _num_denom_count(cases, done, due)

def cf_last_month(cases):
    cf_schedule_in_months = (6, 7, 8, 9, 12, 15, 18)
    cf_schedule = (m * 30 for m in cf_schedule_in_months)
    due = lambda case: len(_visits_due(case, cf_schedule))
    done = lambda case: _visits_done(case, cf_schedule, "cf")
    return _num_denom_count(cases, done, due)

def hd_day(cases):
    valid_cases = filter(lambda case: _delivered_at_in_timeframe(case, 'home', 30), cases)
    denom = len(valid_cases)
    num = len(filter(lambda case:_visited_in_timeframe_of_birth(case, 1) , valid_cases))
    return _num_denom(num, denom)

def id_day(cases):
    valid_cases = filter(lambda case: _delivered_at_in_timeframe(case, ['private', 'public'], 30), cases)
    denom = len(valid_cases)
    num = len(filter(lambda case:_visited_in_timeframe_of_birth(case, 1) , valid_cases))
    return _num_denom(num, denom)

def idnb(cases):
    valid_cases = filter(lambda case: _delivered_at_in_timeframe(case, ['private', 'public'], 30) and
                                      get_related_prop(case, 'birth_status') == "live_birth", cases)
    denom = len(valid_cases)

    def breastfed_hour(case):
        dtf = get_related_prop(case, 'date_time_feed')
        tob = get_related_prop(case, 'time_of_birth')
        if dtf and tob:
            return dtf - tob <= dt.timedelta(hours=1)
        return False

    num = len(filter(lambda case: breastfed_hour(case), valid_cases))
    return _num_denom(num, denom)

def ptlb(cases, num_only=False):
    valid_cases = filter(lambda case: _weak_babies(case), cases)
    denom = len(valid_cases)
    num = len(filter(lambda case: getattr(case, 'term', None) == "pre_term", valid_cases))
    return _num_denom(num, denom) if not num_only else num

def lt2kglb(cases, num_only=False):
    valid_cases = filter(lambda case: _weak_babies(case), cases)
    denom = len(valid_cases)

    def over2(case):
        w = get_related_prop(case, 'weight')
        fw = get_related_prop(case, 'first_weight')
        return (w is not None and w < 2.0) or (fw is not None and fw < 2.0)

    num = len(filter(lambda case: over2(case), valid_cases))
    return _num_denom(num, denom) if not num_only else num

def _get_time_of_birth(form):
    try:
        time_of_birth = form.xpath('form/child_info/case/update/time_of_birth')
        assert time_of_birth is not None
    except AssertionError:
        time_of_birth = safe_index(
            form.xpath('form/child_info')[0],
            'case/update/time_of_birth'.split('/')
        )
    return time_of_birth

def complications(cases, days, now=None):
    """
    DENOM: [
        any DELIVERY forms with (
            complications = 'yes'
        ) in last 30 days
        PLUS any PNC forms with ( # 'any applicable from PNC forms with' (?)
            abdominal_pain ='yes' or
            bleeding = 'yes' or
            discharge = 'yes' or
            fever = 'yes' or
            pain_urination = 'yes'
        ) in the last 30 days
        PLUS any REGISTRATION forms with (
            abd_pain ='yes' or    # == abdominal_pain
            fever = 'yes' or
            pain_urine = 'yes' or    # == pain_urination
            vaginal_discharge = 'yes'    # == discharge
        ) with add in last 30 days
        PLUS any EBF forms with (
            abdominal_pain ='yes' or
            bleeding = 'yes' or
            discharge = 'yes' or
            fever = 'yes' or
            pain_urination = 'yes'
        ) in last 30 days    # note, don't exist in EBF yet, but will shortly
    ]
    NUM: [
        filter (
            DELIVERY ? form.meta.timeStart - child_info/case/update/time_of_birth,
            REGISTRATION|PNC|EBF ? form.meta.timeStart - case.add
        ) < `days` days
    ]
    """
    #https://bitbucket.org/dimagi/cc-apps/src/caab8f93c1e48d702b5d9032ef16c9cec48868f0/bihar/mockup/bihar_pnc.xml
    #https://bitbucket.org/dimagi/cc-apps/src/caab8f93c1e48d702b5d9032ef16c9cec48868f0/bihar/mockup/bihar_del.xml
    #https://bitbucket.org/dimagi/cc-apps/src/caab8f93c1e48d702b5d9032ef16c9cec48868f0/bihar/mockup/bihar_registration.xml
    #https://bitbucket.org/dimagi/cc-apps/src/caab8f93c1e48d702b5d9032ef16c9cec48868f0/bihar/mockup/bihar_ebf.xml
    now = now or dt.datetime.utcnow()
    PNC = 'http://bihar.commcarehq.org/pregnancy/pnc'
    DELIVERY = 'http://bihar.commcarehq.org/pregnancy/del'
    REGISTRATION = 'http://bihar.commcarehq.org/pregnancy/registration'
    EBF = 'https://bitbucket.org/dimagi/cc-apps/src/caab8f93c1e48d702b5d9032ef16c9cec48868f0/bihar/mockup/bihar_ebf.xml'
    _pnc_ebc_complications = [
        'abdominal_pain',
        'bleeding',
        'discharge',
        'fever',
        'pain_urination',
    ]
    complications_by_form = {
        DELIVERY: [
            'complications'
        ],
        PNC: _pnc_ebc_complications,
        EBF: _pnc_ebc_complications,
        REGISTRATION: [
            'abd_pain',
            'fever',
            'pain_urine',
            'vaginal_discharge',
        ],
    }

    debug = defaultdict(int)

    def get_forms(case, days=30):
        xform_ids = set()
        for action in case.actions:
            if action.xform_id not in xform_ids:
                xform_ids.add(action.xform_id)
                if now - dt.timedelta(days=days) <= action.date <= now:
                    try:
                        debug['forms processed'] += 1
                        yield action.xform
                    except ResourceNotFound:
                        pass

    denom = 0
    num = 0
    days = dt.timedelta(days=days)
    for case in filter(lambda case: case.type == 'cc_bihar_pregnancy', cases):
        for form in get_forms(case):
            try:
                complication_paths = complications_by_form[form.xmlns]
            except KeyError:
                continue
            debug['relevent_xmlns'] += 1
            has_complication = False
            has_recent_complication = False
            for p in complication_paths:
                if form.xpath('form/' + p) == 'yes':
                    has_complication = True
                    if form.xmlns == DELIVERY:
                        add = _get_time_of_birth(form)
                    else:
                        add = get_add(case)
                    add = string_to_datetime(add)
                    if form.metadata.timeStart - add < days:
                        has_recent_complication = True
                        break
            if has_complication:
                denom += 1
                if has_recent_complication:
                    num += 1
    return "%s/%s" % (num, denom)
