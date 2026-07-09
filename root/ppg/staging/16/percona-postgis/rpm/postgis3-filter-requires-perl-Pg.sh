#!/bin/sh
/usr/lib/rpm/perl.req "$@" | /bin/grep -v 'Pg\b'
