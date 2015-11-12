USAGE = """

  python scenarioMetrics.py

  Run this from the model run dir.
  Processes model outputs and creates a single csv with scenario metrics, called metrics\scenario_metrics.csv

  This file will have 3 columns:
    1) scenario ID
    2) metric description
    3) metric value

  Metrics are:

"""

import os, sys
import numpy, pandas

def tally_travel_cost(iteration, sampleshare, metrics_dict):
    """
    Adds the following keys to metrics_dict:
    total_transit_fares_inc[1-4] ($2000)
    total_transit_person_trips_inc[1-4]
    total_auto_cost_inc[1-4] ($2000)
    total_auto_person_trips_inc[1-4]
    total_households_inc[1-4]
    """
    print "Tallying travel costs"
    transit_df = pandas.read_csv(os.path.join("metrics","transit_times_by_mode_income.csv"),
                                 sep=",", index_col=[0,1])
    transit_df['Total Cost'] = transit_df['Daily Trips']*transit_df['Avg Cost']
    transit_df = transit_df.sum(level='Income')
    for inc_level in range(1,5):
        metrics_dict['total_transit_fares_inc%d' % inc_level] = transit_df.loc['inc%d' % inc_level, 'Total Cost']
        metrics_dict['total_transit_trips_inc%d' % inc_level] = transit_df.loc['inc%d' % inc_level, 'Daily Trips']

    auto_df = pandas.read_csv(os.path.join("metrics","auto_times.csv"),
                              sep=",", index_col=[0,1])
    auto_df = auto_df.sum(level='Income')
    for inc_level in range(1,5):
        metrics_dict['total_auto_cost_inc%d'  % inc_level] = auto_df.loc['inc%d' % inc_level, ['Total Cost', 'Bridge Tolls', 'Value Tolls']].sum()
        metrics_dict['total_auto_trips_inc%d' % inc_level] = auto_df.loc['inc%d' % inc_level, 'Daily Person Trips']

    # Count households from disaggregate output
    household_df = pandas.read_csv(os.path.join("main", "householdData_%d.csv" % iteration),
                                   sep=",")
    household_df['income_cat'] = 0
    household_df.loc[                                 (household_df['income']< 30000), 'income_cat'] = 1
    household_df.loc[(household_df['income']>= 30000)&(household_df['income']< 60000), 'income_cat'] = 2
    household_df.loc[(household_df['income']>= 60000)&(household_df['income']<100000), 'income_cat'] = 3
    household_df.loc[(household_df['income']>=100000)                                , 'income_cat'] = 4
    household_df['num_hhs'] = 1.0/sampleshare


    for inc_level in range(1,5):
        metrics_dict['total_households_inc%d' % inc_level] = household_df.loc[household_df.income_cat==inc_level, 'num_hhs'].sum()

def tally_access_to_jobs(iteration, sampleshare, metrics_dict):
    """
    Reads in database\TimeSkimsDatabaseAM.csv and filters it to O/Ds with
    da time <= 30 minutes OR wTrnW time <= 45 minutes.

    Joining the dest TAZs to jobs, we find the number of jobs accessible from each TAZ
    (within the travel time windows)
    """
    print "Tallying access to jobs"
    traveltime_df = pandas.read_csv(os.path.join("database","TimeSkimsDatabaseAM.csv"),
                                    sep=",")
    traveltime_df = traveltime_df[['orig','dest','da','wTrnW']]
    # -999 is really no-access
    traveltime_df.replace(to_replace=[-999.0], value=[None], inplace=True)
    len_traveltime_df = len(traveltime_df)

    # look at only those O/D pairs with wTrnW <= 45 OR da <= 30
    traveltime_df = traveltime_df.loc[(traveltime_df.wTrnW <=45)|(traveltime_df.da <=30)]
    print "  Out of %d O/D pairs, %d are accessible within 45 min wTrnW or 30 min da" % (len_traveltime_df, len(traveltime_df))

    # destinations are jobs => find number of jobs accessible from each TAZ within the travel time windows
    tazdata_df = pandas.read_csv(os.path.join("landuse", "tazData.csv"), sep=",")
    tazdata_df = tazdata_df[['ZONE','TOTHH','TOTPOP','EMPRES','TOTEMP']]
    total_emp  = tazdata_df['TOTEMP'].sum()
    total_pop  = tazdata_df['TOTPOP'].sum()

    traveltime_df = pandas.merge(left=traveltime_df, right=tazdata_df[['ZONE','TOTEMP']],
                                 left_on="dest",     right_on="ZONE",
                                 how="left")
    traveltime_df.drop('ZONE', axis=1, inplace=True)  # ZONE == dest

    # aggregate to origin
    traveltime_df_grouped = traveltime_df.groupby(['orig'])
    accessiblejobs_df = traveltime_df_grouped.agg({'da':numpy.mean, 'wTrnW':numpy.mean, 'TOTEMP':numpy.sum})
    # print accessiblejobs_df.head()

    # join persons to origin
    accessiblejobs_df = pandas.merge(left=accessiblejobs_df, right=tazdata_df[['ZONE','TOTPOP']],
                                     left_index=True,         right_on="ZONE",
                                     how="left")
    accessiblejobs_df['TOTEMP_weighted'] = accessiblejobs_df['TOTEMP']*accessiblejobs_df['TOTPOP']
    print accessiblejobs_df.head()
    # numerator = accessible jobs weighted by persons
    #  e.g. sum over TAZs of (totpop at TAZ x totemp jobs accessible)
    # denominator = total jobs weighted by persons
    metrics_dict['jobacc_acc_jobs_weighted_persons']   = accessiblejobs_df['TOTEMP_weighted'].sum()
    metrics_dict['jobacc_total_jobs_weighted_persons'] = total_emp*total_pop
    metrics_dict['jobacc_accessible_job_share']        = float(metrics_dict['jobacc_acc_jobs_weighted_persons']) / float(metrics_dict['jobacc_total_jobs_weighted_persons'])

if __name__ == '__main__':
    pandas.set_option('display.width', 500)
    iteration    = int(os.environ['ITER'])
    sampleshare  = float(os.environ['SAMPLESHARE'])

    metrics_dict = {}
    tally_travel_cost(iteration, sampleshare, metrics_dict)
    tally_access_to_jobs(iteration, sampleshare, metrics_dict)

    for key in sorted(metrics_dict.keys()):
        print "%35s => %f" % (key, metrics_dict[key])