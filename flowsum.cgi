#!/usr/bin/perl

use strict;
use warnings;

use CGI;
use DBI;
use Config::General;

my $title = 'Flowsum';

$CGI::DISABLE_UPLOADS = 1;
$CGI::POST_MAX        = 1024;
$|=1;

my $MIN_MEGS = 0.01;
my $MIN_PACKETS = 3;
my $DEFAULT_PERIOD = 3600;

my $q = new CGI;

print $q->header(),
      $q->start_html($title),
      $q->h1($title);

my $cfgobj = new Config::General('/usr/local/etc/flowsum2cgi.conf');
my %config = $cfgobj->getall;

my $time1 =    $q->param('time1')  || '';
my $time2 =    $q->param('time2')  || '';
my $period=    $q->param('period') || ($time1 || $time2 ? '' : $DEFAULT_PERIOD);
my $ipaddr=    $q->param('ipaddr') || '';
my $order = lc($q->param('order')  || 'datetime');  # trafmegs, ipaddr, datetime 
my $step  = lc($q->param('step')   || 'nostep');    # autostep, hour, minute, day, month

$period = 3600*24*30 if lc($period) eq 'month';
$period = 3600*24*7  if lc($period) eq 'week';
$period = 3600*24    if lc($period) eq 'day';
$period = 3600       if lc($period) eq 'hour';

#===============================================================

print << "END_FORM";
<p>
<form method='get' action=''>
<table border='0' colspan='4'>
<tr><td align='right'>Start datetime:</td>
    <td><input name='time1' value='$time1'/></td>
    <td>(example: <b>2012-01-02 12:00</b>)</td>
</tr>
<tr><td align='right'>End datetime:</td><td>
    <input name='time2' value='$time2'/></td>
    <td>(optional)</td>
</tr>
<tr><td align='right'>...or interval:</td>
     <td><input name='period' value='$period'/></td>
     <td>(example: <b>3600</b> = last hour, <b>86400</b> = last day)</td>
</tr>
<tr><td align='right'>IP-address:</td>
    <td><input name='ipaddr' value='$ipaddr'/></td>
    <td>(optional)</td>
</tr>
<tr><td align='right'>Order:</td>
    <td><select name='order'>
        <option value='datetime'>Date/Time</option>
        <option value='trafmegs'>Traffic Usage</option>
        <option value='ipaddr'  >IP-Address</option>
        </select></td>
    <td>(current: <b>$order</b>)</td>
</tr>
<tr><td align='right'>Date/Time Step:</td>
    <td><select name='step'>
        <option value='nostep'>Not Used</option>
        <option value='autostep'>Auto</b></option>
        <option>Minute</option>
        <option>Hour</option>
        <option>Day</option>
        <option>Month</option>
        </select></td>
    <td>(group by Date/Type or by IP-Address)</td>
</tr>
<tr><td colspan='2' align='center'><input type='submit' value='Filter!'></td>
    <td></td>
</tr>
</table>
</form>
</p>
END_FORM

unless ($period or ($time1 || $time2)) {
	print "<font color='red'><b>Period or time required!</b></font>\n";
	print $q->end_html;
	exit;
}

#===============================================================


my $dbh = DBI->connect(
	"DBI:mysql:database=".($config{DBNAME} || 'traffic')
	            .":host=".($config{DBHOST} || 'localhost'),
	$config{DBUSER} || 'flowsum2cgi',
	$config{DBPASS})
	or die "Cannot connect to database ".$DBI::errstr."\n";

sub dbquery($;@)
{
	my $query = shift;
	my $sth = $dbh->prepare($query)
		or die "Cannot prepare '$query': ".$dbh->errstr."\n";
	$sth->execute(@_) or die "Cannot execute '$query': ".$sth->errstr."\n";
	$sth;
}

sub cgitable_header
{
	print "<table cellpadding='6' border='1'><tr>\n";
	print join('',map("  <th align='center'>$_</th>\n", @_));
	print "</tr>\n\n";
}

sub td($;$) { "<td align='".($_[1] || 'left')."'>".(defined $_[0] ? $_[0] : '')."</td>" }

#===============================================================

my ($filter, @args, @hint);
if ($time1 and $time2) {
	if ($time1 gt $time2) { my $a = $time1; $time1 = $time2; $time2 = $a; }
	$filter = "ftime >= unix_timestamp(?) and ftime < unix_timestamp(?)";
	push @args, $time1, $time2;
	$period = $time2 - $time1;
	push @hint, "between $time1 and $time2";
} elsif ($time1 and $period) {
	$filter = "ftime >= unix_timestamp(?) and ftime < unix_timestamp(?) + ?";
	push @args, $time1, $time1, $period;
	push @hint, "$period seconds since $time1";
} elsif ($time2 and $period) {
	$filter = "ftime >= unix_timestamp(?)-? and ftime < unix_timestamp(?)";
	push @args, $time2, $period, $time2;
	push @hint, "$period seconds before $time2";
} elsif ($time1 ||= $time2) {
	print "<!-- point 2 -->\n";
	$filter = "ftime >= unix_timestamp(?)";
	push @args, $time1;
	push @hint, "since $time1 till now";
} elsif ($period ||= $DEFAULT_PERIOD) {
	$filter = "ftime >= unix_timestamp() - ?";
	push @args, $period;
	push @hint, "last $period seconds";
}
if ($ipaddr) {
	$filter .= " and ipaddr=inet_aton(?)";
	push @args, $ipaddr;
	push @hint, "ip $ipaddr";
}

if ($order eq 'datetime') {
	$order = 'ftime, ltime, tclass';
	push @hint, "order by date";
} elsif ($order eq 'trafmegs') {
	$order = 'summegs desc';
	push @hint, "order by traffic";
} elsif ($order eq 'ipaddr') {
	# directly passed
} else {
	die "Wrong order $order, aborted.";
}

my $stepfmt = '';
if      ($step eq 'minute' or ($step eq 'autostep' and $period <= 3600)) {
	$stepfmt = '%Y-%m-%d %H:%i';
	push @hint, "minute step";
} elsif ($step eq 'hour'   or ($step eq 'autostep' and $period <= 3600*24)) {
	$stepfmt = '%Y-%m-%d %H:xx';
	push @hint, "hourly step";
} elsif ($step eq 'day'    or ($step eq 'autostep' and $period <= 3600*24*31)) {
	$stepfmt = '%Y-%m-%d';
	push @hint, "daily step";
} elsif ($step eq 'month'  or ($step eq 'autostep' and $period <= 3600*24*366)) {
	$stepfmt = '%Y-%m';
	push @hint, "monthly step";
}

#===============================================================

print << "FILTER_LIST";
<!--
Filter settings:
time1 = $time1
time2 = $time2
period = $period
ipaddr = $ipaddr
order = $order
step = $step
stepfmt = $stepfmt
filter = "$filter"
filter_args = @args
FILTER_LIST
#print "$_ = $ENV{$_}\n" foreach sort keys %ENV;
print "-->\n";

print "<p><h3>Display mode:</h3><ul>\n";
print "<li>$_</li>\n" foreach @hint;
print "</ul></p>\n";

#===============================================================

my ($n, $totalmegs) = (0, 0);

if ($stepfmt) {
	cgitable_header('#', qw/DateTime TC_ID Megs Packets/);

	my $sth = dbquery("select date_format(from_unixtime(ftime), '$stepfmt') as dt,"
		." round(sum(bytes) / 1024 / 1024, 2) as summegs,"
		." sum(packets) as sumpackets,"
		." tclass"
		." from ".( $config{DBTABLE} || 'flowsum' )." where $filter"
		." group by dt,tclass"
#		." having summegs    > $MIN_MEGS"
		." having sumpackets > $MIN_PACKETS"
		." order by $order", @args
	);

	while (my $r = $sth->fetchrow_hashref) {
		print "<tr>"
		     .td(++$n,'right')
		     .td($r->{dt})
		     .td($r->{tclass})
		     .td($r->{summegs},  'right')
		     .td($r->{sumpackets},'right')
		     ."</tr>\n";
		$totalmegs += $r->{summegs};
	}
} else {
	cgitable_header('#', qw/User IP TC_ID Megs Packets First Last/);

	my $sth = dbquery("select uid, inet_ntoa(ipaddr) as ipstr, tclass,"
		." round(sum(bytes) / 1024 / 1024, 2) as summegs,"
		." sum(packets) as sumpackets,"
		." from_unixtime(min(ftime)) as ftm, from_unixtime(max(ltime)) as ltm"
		." from ".( $config{DBTABLE} || 'flowsum' )." where $filter"
		." group by ipaddr,tclass"
#			." having summegs    > $MIN_MEGS"
		." having sumpackets > $MIN_PACKETS"
		." order by $order", @args);
	while (my $r = $sth->fetchrow_hashref) {
		print "<tr>"
		     .td(++$n,'right')
		     .td($r->{uid})
		     .td($r->{ipstr})
		     .td($r->{tclass})
		     .td($r->{summegs},  'right')
		     .td($r->{sumpackets},'right')
		     .td($r->{ftm})
		     .td($r->{ltm})
		     ."</tr>\n";
		$totalmegs += $r->{summegs};
	}
}

print "</table>\n";
print "<p>Total <b>$totalmegs</b> megs.</p><p><i>".localtime.".</i></p>\n";
print $q->end_html;

## EOF ##
