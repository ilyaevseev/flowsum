-- flowsum2sql --

create table flowsum(
	    uid integer unsigned not null default 0,
	 ipaddr integer unsigned not null default 0,
	 tclass integer unsigned not null default 0,
	  bytes  bigint unsigned not null default 0,
	packets integer unsigned not null default 0,
	  ftime integer unsigned not null default 0,
	  ltime integer unsigned not null default 0,
	key(ipaddr,ftime,ltime)
);

grant insert on traffic.flowsum to flowsum2sql@localhost identified by 'SecretPass1';
grant select on traffic.flowsum to flowsum2cgi@localhost identified by 'SecretPass2';
grant select,insert,delete
             on traffic.flowsum to flowsum2sum@localhost identified by 'SecretPass3';

-- END --
