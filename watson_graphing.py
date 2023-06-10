#!/usr/bin/env python3
"""Exports data from Watson (http://tailordev.github.io/Watson/), then creates a
stacked bar chart of hours spent by tag and/or project

NOTE: Only one combined legend will be shown. This is an issue with Plotly.
https://community.plotly.com/t/plotly-subplots-with-individual-legends/1754/18
"""


import argparse
import tempfile
import subprocess
import math
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def parse_args(args):
    """Prefix specific user args for Watson with `--`"""

    # The following args require `--` before it
    flag_args = ['c', 'current', 'C', 'no-current', 'r', 'reverse', 'R',
                 'no-reverse', 'f', 'from', 't', 'to', 'y', 'year', 'm',
                 'month', 'l', 'luna', 'w', 'week', 'd', 'day', 'a', 'all',
                 'p', 'project', 'T', 'tag', 'ignore-project', 'ignore-tag']

    watson_args_parsed = []
    for arg in args.WATSON_ARGS:
        if arg in flag_args:
            # Watson flag arg, so prefix it with `--`
            watson_args_parsed.append('--' + arg)
        else:
            # Watson non-flag arg, so don't prefix it
            watson_args_parsed.append(arg)

    return watson_args_parsed


def striplist(lst):
    """Strips spaces from each element of a list"""

    if type(lst) == list:
        return ([x.strip() for x in lst])
    else:
        return lst


def find_location(lst):
    """Returns location, identified as first list item beginning with '@'"""

    if type(lst) == list:
        for i in lst:
            if i[0] == '@':
                return i


def find_attributes(lst):
    """Returns attributes, identified as not beginning with '@'"""

    attributes = []
    if type(lst) == list:
        for i in lst:
            if i[0] != '@':
                attributes.append(i)
    return attributes


def graph(args):
    """Generate graphs"""

    watson_args_parsed = parse_args(args)

    # Export Watson data to temporary file
    with tempfile.TemporaryFile() as output:
        subprocess.run(['watson', 'log', '--csv'] + watson_args_parsed,
                       stdout=output, check=True)
        output.seek(0)
        df = pd.read_csv(output, parse_dates=['start', 'stop'])

    # Parse data from CSV and generate additional time fields
    df['time'] = (df['stop'] - df['start']).dt.seconds.div(3600)
    if args.period == 'week':
        df['date'] = df['start'].dt.to_period('W').dt.to_timestamp()  # works, gives dates
        # df['date'] = df['start'].dt.strftime('%Y-%U')  # works, gives week number
    elif args.period == 'month':
        df['date'] = df['start'].dt.to_period('M').dt.to_timestamp()
        # df['date'] = df['start'].dt.strftime('%Y-%m')  # works
    elif args.period == 'quarter':
        df['date'] = df['start'].dt.to_period('Q').dt.to_timestamp()
        # df['date'] = df['start'].dt.strftime('%Y-%q')  # runs, but wrong x-axis
    elif args.period == 'year':
        df['date'] = df['start'].dt.to_period('Y').dt.to_timestamp()
        # df['date'] = df['start'].dt.strftime('%Y')  # works
    else:
        df['date'] = df['start'].dt.date

    # Attributes and locations: split tags into a list and remove spaces
    df['tags_list'] = df['tags'].str.split(',').apply(striplist)

    # Get attributes my merging non-locations back into a string
    df['attributes'] = df['tags_list'].apply(find_attributes).str.join(', ')

    # Get location by finding first item beginning with "@"
    df['location'] = df['tags_list'].apply(find_location)

    # Truncate project names if requested
    if args.truncate:
        df['project'].replace(to_replace=r'\..*', value='', inplace=True,
                              regex=True)

    # Determine which subplots (hours, project, tags) to generate subplots for
    if args.plot == 'all':
        subplots = ['hours', 'project', 'attributes', 'location']
    else:
        subplots = args.plot

    # Create subplot titles
    if args.date:
        date_range = str(min(df['date'])) + ' to ' + str(max(df['date']))
    plot_titles = []
    for plot in subplots:
        if args.date:
            plot_titles.append(plot.title() + ': ' + date_range)
        else:
            plot_titles.append(plot.title())

    # Page 1: subplots showing time spent by project over time
    # https://plotly.com/python-api-reference/generated/plotly.subplots.make_subplots.html
    fig = make_subplots(
        rows=len(subplots),
        cols=1,
        shared_xaxes=False,  # set to True to hide dates on all but bottom plot
        subplot_titles=plot_titles,
        x_title= 'Watson command: ' + ' '.join(watson_args_parsed)
        )

    # Populate each subplot
    for id, plot in enumerate(subplots):

        if plot == 'hours':
            # Convert time from minutes to hours
            df_groupby_date = df.groupby('date').sum()

            # Add dates and times to the figure (for this label)
            fig.add_trace(go.Scatter(name='hours',
                                     x=df_groupby_date.index,
                                     y=df_groupby_date['time'],
                                     mode='lines+markers',
                                     legendgroup = plot,  # remove when a better solution is available
                                    ),
                          row=id+1, col=1)
            fig.update_yaxes(title_text='Hours',
                             row=id+1,
                             col=1,
                             range=[0, math.ceil(max(df_groupby_date['time']))]
                            )
        else:
            # Fill in no tag entries with 'None'
            df.fillna(value='None', inplace=True)

            # Sort by time or plot
            if args.sort == 'time':
                df_type_sorted = df.groupby(plot).sum().sort_values(
                    by='time').index.values[::-1]  # most time (bottom) to least time (top)
            elif args.sort == 'name':
                df_type_sorted = df.groupby(plot).sum().sort_values(
                    by=plot).index.values[::-1]  # alphabetical order from top to bottom

            for label in df_type_sorted:  # `label` is the name of a project or tag
                # For each label, add dates and times to the figure

                # For frames matching label, group by the date and sum the time spent
                df_group = df[df[plot] == label].groupby('date').sum()

                # Add dates and times to the figure (for this label)
                fig.add_trace(go.Bar(name=label,
                                     x=df_group.index,
                                     y=df_group['time'],
                                     legendgroup = plot,  # remove when a better solution is available
                                    ),
                              row=id+1, col=1)
                fig.update_yaxes(title_text='Hours', row=id+1, col=1)

    # Change the bar mode
    # https://plotly.com/python/bar-charts/#stacked-bar-chart
    fig.update_layout(barmode='stack',
                      legend_tracegroupgap = 100,  # remove when a better solution is available
                     )

    # If only showing one subplot, include a slider for zooming in
    if len(subplots) == 1:
        fig.update_layout(
            xaxis=dict(
                rangeselector=dict(
                    buttons=list([
                        dict(count=1,
                             label="1m",
                             step="month",
                             stepmode="backward"),
                        dict(count=6,
                             label="6m",
                             step="month",
                             stepmode="backward"),
                        dict(count=1,
                             label="YTD",
                             step="year",
                             stepmode="todate"),
                        dict(count=1,
                             label="1y",
                             step="year",
                             stepmode="backward"),
                        dict(step="all")
                    ])
                ),
                rangeslider=dict(
                    visible=True,
                ),
                type="date"
            )
        )
    fig.show()
    if args.save:
        fig.write_image('watson_graphing_1.png', width=1920, height=1080)

    # Page 2: time spent by project
    if args.totals:
        fig = go.Figure(layout={'title':'Time Spent by Project'})
        by_project = df.groupby('project').sum().sort_values(by='project').sort_values(by='time', ascending=False)
        fig.add_trace(go.Bar(x=by_project.index, y=by_project['time'].values))
        fig.show()
        if args.save:
            fig.write_image('watson_graphing_2.png', width=1920, height=1080)


def main():
    """Get arguments from user"""

    parser = argparse.ArgumentParser(
            description='Create graph from Watson data')

    parser.add_argument('--plot',
                        nargs='+',
                        choices=['hours', 'project', 'attributes', 'location', 'all'],
                        default='all',
                        help='Plots to display, defaults to all; shows slider if only one plot selected')
    parser.add_argument('--totals',
                        action='store_true',
                        help='Show a second page with a graph of total hours by project')
    parser.add_argument('--period',
                        choices=['day', 'week', 'month', 'quarter', 'year'],
                        default='day',
                        help='Date grouping, defaults to day')
    parser.add_argument('--sort',
                        choices=['time', 'name'],
                        default='time',
                        help='Sort projects/tags by decreasing time or alphabetically by name')
    parser.add_argument('--truncate',
                        action='store_true',
                        help='Remove all text in project after the first '
                        'period (useful for combining subprojects')
    parser.add_argument('--date',
                        action='store_true',
                        help='Display the date range in the plot titles')
    parser.add_argument('--save',
                        action='store_true',
                        help='Save graphs as .png files')
    parser.add_argument('WATSON_ARGS',
                        nargs='*',
                        help='Arguments for `watson log [WATSON_ARGS] --csv` '
                        'without any hyphens, such as `week current`; '
                        'run `watson log --help` for full list of options')
    args = parser.parse_args()

    graph(args)


if __name__ == "__main__":
    main()
